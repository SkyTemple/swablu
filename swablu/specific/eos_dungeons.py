"""
This bot provides dungeon preview images based on dungeon floor descriptions.

Submit a message with a dungeon floor XML file and you will receive a reply with the rendered dungeon.

If the message contains no attachment it is ignored, so you can also just chat and discuss floor layouts in
this channel.

Each message needs at least one attachment:
  - A single XML file: The dungeon floor description as exported from SkyTemple. Fixed room settings are ignored.

It can also contain a second attach:
  - A ZIP file which is a DTEF ZIP archive as exported from SkyTemple.
    The dungeon is rendered using the tileset in the archive.
  - If the second file is missing the tileset is taken from the floor definition + a vanilla EoS game.

The following strings can be contained in the message and change how the floor is drawn:
  - `+onlyfloor`: Shortcut for all of these flags:
      - `+nostairs`: Disables stair rendering
      - `+nomonsters`: Disables monster rendering
      - `+noflooritems`: Disables floor item rendering
      - `+notraps`: Disables trap rendering
  - `+nokecleon`: Disables rendering the Kecleon shop
  - `+burieditems`: Shows buried items
  - `+nopatches`: Renders the floor as if the "UnusedDungeonChancePatch" patch is not applied
  - `+seed:<seed>`: Sets the seed for the random number generator.

Example: "+onlyfloor +nokecleon +seed:12345"
"""
import logging
import os
import random
import shutil
import traceback
from contextlib import contextmanager
from io import BytesIO
from tempfile import TemporaryDirectory
from typing import Optional, ContextManager, Tuple, List, Union
from xml.etree import ElementTree
from xml.etree.ElementTree import ParseError
from zipfile import ZipFile

import cairo
from PIL import Image
from discord import TextChannel, Message, Embed, Colour, Attachment, File
from ndspy.rom import NintendoDSRom

from skytemple_files.common.impl_cfg import change_implementation_type, ImplementationType
from skytemple_files.dungeon_data.mappa_bin.mappa_xml import mappa_floor_from_xml

change_implementation_type(ImplementationType.NATIVE)

from skytemple_dtef.explorers_dtef import ExplorersDtef
from skytemple_dtef.explorers_dtef_importer import ExplorersDtefImporter
from skytemple_files.common.dungeon_floor_generator.generator import DungeonFloorGenerator, Tile, RandomGenProperties, \
    TileType, SIZE_Y, SIZE_X, RoomType
from skytemple_files.common.ppmdu_config.xml_reader import Pmd2XmlReader
from skytemple_files.common.types.file_types import FileType
from skytemple_files.common.xml_util import XmlValidateError
from skytemple_files.container.bin_pack.model import BinPack
from skytemple_files.container.dungeon_bin.model import DungeonBinPack
from skytemple_files.data.item_p.protocol import ItemPProtocol
from skytemple_files.data.md.protocol import MdProtocol
from skytemple_files.dungeon_data.fixed_bin.model import DirectRule, FixedFloor, TileRuleType, TileRule, FloorType, \
    EntityRule
from skytemple_files.dungeon_data.mappa_bin.protocol import MappaFloorProtocol, GUARANTEED, POKE_ID, MappaTrapType
from skytemple_files.graphics.dma.dma_drawer import DmaDrawer
from skytemple_files.graphics.dma.protocol import DmaType
from skytemple_files.graphics.dpc import DPC_TILING_DIM
from skytemple_files.graphics.dpci import DPCI_TILE_DIM
from skytemple_files.graphics.img_itm.model import ImgItm
from skytemple_files.graphics.img_trp.model import ImgTrp
from skytemple_files.graphics.wan_wat.model import Wan
from skytemple_rust.st_dma import Dma
from skytemple_rust.st_dpc import Dpc
from skytemple_rust.st_dpci import Dpci
from skytemple_rust.st_dpl import Dpl
from skytemple_rust.st_dpla import Dpla

if __name__ != "__main__":
    from swablu.config import discord_writes_enabled, discord_client, DISCORD_CHANNEL_FLOOR_GENERATOR_BOT

logger = logging.getLogger(__name__)
DTEF_XML_NAME = "tileset.dtef.xml"
DTEF_VAR0_FN = 'tileset_0.png'
DTEF_VAR1_FN = 'tileset_1.png'
DTEF_VAR2_FN = 'tileset_2.png'
STATIC_DATA = Pmd2XmlReader.load_default()
ITEM_CATEGORIES = STATIC_DATA.dungeon_data.item_categories
ITEM_CATEGORIES_BY_NAME = {x.name: x for x in ITEM_CATEGORIES.values()}


class UserError(Exception):
    def __init__(self, title: str, message: str):
        self.title = title
        self.message = message


def asset_path() -> str:
    return os.environ["EOS_DUNGEONS_TILESET_PATH"]


class DtefProvider:
    def __init__(self, potential_zip_file_bytes: Optional[bytes], tileset_id: int):
        self.zip_file = None
        self.tileset_id = tileset_id
        self.zip_tmp_ctx: Optional[ContextManager] = None
        if potential_zip_file_bytes is not None:
            # Read potential_zip_file_bytes as a zip file
            self.zip_file = ZipFile(BytesIO(potential_zip_file_bytes))

    def __enter__(self):
        path: str

        if self.zip_file is not None:
            self.zip_tmp_ctx = TemporaryDirectory()
            path = self.zip_tmp_ctx.__enter__()
            for file in self.zip_file.namelist():
                if "\\" in file or "/" in file:
                    raise UserError("Invalid ZIP file", "The DTEF ZIP file may not contain sub-directories.")
                self.zip_file.extract(file, path)
        else:
            path = os.path.join(asset_path(), "dtef", str(self.tileset_id))
            if not os.path.exists(path):
                raise UserError("Invalid Tileset", f"The tileset with ID {self.tileset_id} does not exist.")

        return path

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.zip_tmp_ctx is not None:
            self.zip_tmp_ctx.__exit__(exc_type, exc_val, exc_tb)


def dungeon_data_files() -> Tuple[Dma, Dpc, Dpci, Dpl, Dpla]:
    with open(os.path.join(asset_path(), "base.dma"), "rb") as f:
        dma = FileType.DBIN_SIR0_AT4PX_DMA.deserialize(f.read())
    with open(os.path.join(asset_path(), "base.dpc"), "rb") as f:
        dpc = FileType.DBIN_AT4PX_DPC.deserialize(f.read())
    with open(os.path.join(asset_path(), "base.dpci"), "rb") as f:
        dpci = FileType.DBIN_AT4PX_DPCI.deserialize(f.read())
    with open(os.path.join(asset_path(), "base.dpl"), "rb") as f:
        dpl = FileType.DPL.deserialize(f.read())
    with open(os.path.join(asset_path(), "base.dpla"), "rb") as f:
        dpla = FileType.DBIN_SIR0_DPLA.deserialize(f.read())

    return dma, dpc, dpci, dpl, dpla


class Options:
    def __init__(self, message: str):
        self.stairs = True
        self.monsters = True
        self.flooritems = True
        self.traps = True

        self.kecleon = True
        self.burieditems = False
        self.patches = True
        self.seed = random.randint(0, 2 ** 32 - 1)

        for part in message.split(" "):
            part = part.strip()
            if part == "":
                continue
            if part == "+onlyfloor":
                self.stairs = False
                self.monsters = False
                self.flooritems = False
                self.traps = False
            elif part == "+nostairs":
                self.stairs = False
            elif part == "+nomonsters":
                self.monsters = False
            elif part == "+noflooritems":
                self.flooritems = False
            elif part == "+notraps":
                self.traps = False
            elif part == "+nokecleon":
                self.kecleon = False
            elif part == "+burieditems":
                self.burieditems = True
            elif part == "+nopatches":
                self.patches = False
            elif part.startswith("+seed:"):
                self.seed = int(part[6:])
            else:
                raise UserError("Invalid Option", f"Unknown option: {part}")


async def start():
    if not discord_writes_enabled():
        return

    try:
        channel: TextChannel = discord_client.get_channel(DISCORD_CHANNEL_FLOOR_GENERATOR_BOT)

        first_message_by_me: Optional[Message] = None
        async for message in channel.history(limit=50, oldest_first=True):
            if message.author.id == discord_client.user.id:
                first_message_by_me = message
                break

        if first_message_by_me is not None:
            await first_message_by_me.edit(content=__doc__)
        else:
            await channel.send(content=__doc__)

    except Exception as exc:
        logger.exception(f"Failed setting up eos_dungeons for channel {DISCORD_CHANNEL_FLOOR_GENERATOR_BOT}.",
            exc_info=exc)


async def process_message(message: Message) -> bool:
    if not discord_writes_enabled():
        return

    if message.author.id == discord_client.user.id:
        return False

    if message.channel.id != DISCORD_CHANNEL_FLOOR_GENERATOR_BOT:
        return False

    if len(message.attachments) < 1:
        return False

    with message.channel.typing():
        channel: TextChannel = message.channel

        try:
            options = Options(message.content)

            floor_xml_bytes: Optional[bytes] = None
            dtef_zip_bytes: Optional[bytes] = None

            for attachment in message.attachments:
                attachment: Attachment
                if attachment.filename.lower().endswith(".xml"):
                    if floor_xml_bytes is not None:
                        raise UserError("Invalid attachments.", "You attached multiple XML files. Please only attach one.")
                    floor_xml_bytes = await attachment.read()
                elif attachment.filename.lower().endswith(".zip"):
                    if dtef_zip_bytes is not None:
                        raise UserError("Invalid attachments.", "You attached multiple ZIP files. Please only attach one.")
                    dtef_zip_bytes = await attachment.read()
                else:
                    raise UserError("Invalid attachments.", "Attach only one XML file and optionally one ZIP file.")

            if floor_xml_bytes is None:
                raise UserError("Invalid attachments.", "You did not attach a floor XML file. Please attach a floor XML file as well.")

            try:
                xml = ElementTree.parse(BytesIO(floor_xml_bytes)).getroot()
            except ParseError as er:
                raise UserError("XML Error", f"The floor XML you provided can't be parsed: {str(er)}")

            try:
                floor: MappaFloorProtocol = mappa_floor_from_xml(xml, ITEM_CATEGORIES_BY_NAME)
            except XmlValidateError as er:
                raise UserError("XML Error", f"The floor XML you provided is invalid: {str(er)}")

            with DtefProvider(dtef_zip_bytes, floor.layout.tileset_id) as dtef_dir_name:
                for fname in [DTEF_XML_NAME, DTEF_VAR0_FN, DTEF_VAR1_FN, DTEF_VAR2_FN]:
                    if not os.path.exists(os.path.join(dtef_dir_name, DTEF_XML_NAME)):
                        raise UserError("DTEF Error", f"The DTEF ZIP you provided does not contain a {fname} file.")

                tileset: Tuple[Dma, Dpc, Dpci, Dpl, Dpla] = dungeon_data_files()
                importer = ExplorersDtefImporter(*tileset)
                try:
                    importer.do_import(
                        dtef_dir_name,
                        os.path.join(dtef_dir_name, DTEF_XML_NAME),
                        os.path.join(dtef_dir_name, DTEF_VAR0_FN),
                        os.path.join(dtef_dir_name, DTEF_VAR1_FN),
                        os.path.join(dtef_dir_name, DTEF_VAR2_FN)
                    )
                except ValueError as er:
                    raise UserError("DTEF Error", f"The DTEF ZIP you provided is invalid: {str(er)}")

                # Now we can finally draw :pogcash:
                png_file = generate_floor(options, floor, tileset)

                await channel.send(file=File(png_file, "floor.png"))

        except UserError as err:
            await channel.send(embed=Embed(
                title=err.title,
                description=err.message,
                colour=Colour.red()
            ))
        except Exception:
            await channel.send(embed=Embed(
                title="Internal Error",
                description=f"Oh oh! There was an internal error while trying to process your message:\n\n```\n{traceback.format_exc()}\n```",
                colour=Colour.dark_red()
            ))

        return True


####################################
# Actual drawing code, forked from SkyTemple
TRAP_PALETTE_MAP = {
    MappaTrapType.UNUSED.value: 0,
    MappaTrapType.MUD_TRAP.value: 1,
    MappaTrapType.STICKY_TRAP.value: 1,
    MappaTrapType.GRIMY_TRAP.value: 1,
    MappaTrapType.SUMMON_TRAP.value: 1,
    MappaTrapType.PITFALL_TRAP.value: 0,
    MappaTrapType.WARP_TRAP.value: 1,
    MappaTrapType.GUST_TRAP.value: 1,
    MappaTrapType.SPIN_TRAP.value: 1,
    MappaTrapType.SLUMBER_TRAP.value: 1,
    MappaTrapType.SLOW_TRAP.value: 1,
    MappaTrapType.SEAL_TRAP.value: 1,
    MappaTrapType.POISON_TRAP.value: 1,
    MappaTrapType.SELFDESTRUCT_TRAP.value: 1,
    MappaTrapType.EXPLOSION_TRAP.value: 1,
    MappaTrapType.PP_ZERO_TRAP.value: 1,
    MappaTrapType.CHESTNUT_TRAP.value: 0,
    MappaTrapType.WONDER_TILE.value: 0,
    MappaTrapType.POKEMON_TRAP.value: 1,
    MappaTrapType.SPIKED_TILE.value: 0,
    MappaTrapType.STEALTH_ROCK.value: 1,
    MappaTrapType.TOXIC_SPIKES.value: 1,
    MappaTrapType.TRIP_TRAP.value: 0,
    MappaTrapType.RANDOM_TRAP.value: 1,
    MappaTrapType.GRUDGE_TRAP.value: 1,
    27: 0,  # Stairs down
    28: 0,  # Stairs up
    29: 1,  # Rescue Point
    30: 1,  # Kecleon Shop
    31: 0,  # Key Wall
    32: 0,  # Pitfall trap, destroyed
    33: 1,  # X?
}
TRP_FILENAME = 'traps.trp.img'
ITM_FILENAME = 'items.itm.img'


def generate_floor(options: Options, in_floor: MappaFloorProtocol, tileset: Tuple[Dma, Dpc, Dpci, Dpl, Dpla]) -> BytesIO:
    try:
        rng = random.Random(int(options.seed))
    except ValueError:
        rng = random.Random(hash(options.seed))

    floor: List[Tile] = DungeonFloorGenerator(
        unknown_dungeon_chance_patch_applied=options.patches,
        gen_properties=RandomGenProperties.default(rng)
    ).generate(in_floor.layout, max_retries=3, flat=True)
    if floor is None:
        raise UserError("Internal Error", "The floor generator failed to generate a floor from these settings.")

    actions = []
    warnings = set()
    open_guaranteed_floor = set(x for x, y in in_floor.floor_items.items.items() if y == GUARANTEED)
    open_guaranteed_buried = set(x for x, y in in_floor.buried_items.items.items() if y == GUARANTEED)
    for x in floor:
        idx = None
        if x.typ == TileType.PLAYER_SPAWN:
            idx = 1  # bulbasaur
        if x.typ == TileType.ENEMY:
            ridx = rng.randrange(0, 10000)
            last = 383  # Kecleon - fallback
            invalid = True
            for m in in_floor.monsters:
                if m.main_spawn_weight > ridx and m.main_spawn_weight != 0:
                    last = m.md_index
                    invalid = False
                    break
            idx = last
        if x.typ == TileType.ITEM and len(open_guaranteed_floor) > 0:
            idx = open_guaranteed_floor.pop()
        if x.typ == TileType.BURIED_ITEM and len(open_guaranteed_buried) > 0:
            idx = open_guaranteed_buried.pop()
        if x.typ == TileType.ITEM or x.typ == TileType.BURIED_ITEM:
            ridx_cat = rng.randrange(0, 10000)
            ridx_itm = rng.randrange(0, 10000)
            last_cat = 6  # Poké - fallback
            last_item = POKE_ID  # Poké - fallback
            item_list = in_floor.floor_items
            if x.typ == TileType.BURIED_ITEM:
                item_list = in_floor.buried_items
            for c, prop in item_list.categories.items():
                if prop > ridx_cat and prop != 0:
                    last_cat = c
                    break
            for itm, prop in item_list.items.items():
                if prop > ridx_itm and prop != GUARANTEED and prop != 0 and itm in ITEM_CATEGORIES[last_cat].item_ids():
                    last_item = itm
                    break
            idx = last_item
        if x.typ == TileType.TRAP:
            ridx = rng.randrange(0, 10000)
            last = 0  # fallback
            for trap, weight in in_floor.traps.weights.items():
                if weight > ridx and weight != 0:
                    last = trap
                    break
            idx = last
        actions.append(DirectRule(x, idx))

    fixed_floor = FixedFloor.new(SIZE_Y, SIZE_X, actions)
    return FixedRoomDrawer(options, fixed_floor, *tileset).draw_to_png()


class FixedRoomDrawer:
    def __init__(
            self, options: Options, fixed_floor: FixedFloor, dma: Dma, dpc: Dpc, dpci: Dpci, dpl: Dpl, _dpla: Dpla
    ):
        self.dma = dma
        self.dpci = dpci
        self.dpc = dpc
        self.dpl = dpl

        self.options = options
        self.fixed_floor = fixed_floor

        self.mouse_y = 99999

        self.sprite_provider = SpriteProvider()

    def draw_to_png(self) -> BytesIO:
        size_w = (self.fixed_floor.width + 10) * DPC_TILING_DIM * DPCI_TILE_DIM
        size_h = (self.fixed_floor.height + 10) * DPC_TILING_DIM * DPCI_TILE_DIM

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size_w, size_h)
        ctx: cairo.Context = cairo.Context(surface)

        ctx.set_antialias(cairo.Antialias.NONE)

        # Iterate over floor and render it
        rules = []
        draw_outside_as_second_terrain = any(action.tr_type == TileRuleType.SECONDARY_HALLWAY_VOID_ALL
                                             for action in self.fixed_floor.actions if isinstance(action, TileRule))
        outside = DmaType.WATER if draw_outside_as_second_terrain else DmaType.WALL
        rules.append([outside] * (self.fixed_floor.width + 10))
        rules.append([outside] * (self.fixed_floor.width + 10))
        rules.append([outside] * (self.fixed_floor.width + 10))
        rules.append([outside] * (self.fixed_floor.width + 10))
        rules.append([outside] * (self.fixed_floor.width + 10))
        ridx = 0
        for y in range(0, self.fixed_floor.height):
            row = [outside, outside, outside, outside, outside]
            rules.append(row)
            for x in range(0, self.fixed_floor.width):
                action = self.fixed_floor.actions[ridx]
                if isinstance(action, TileRule):
                    if action.tr_type.floor_type == FloorType.FLOOR:
                        row.append(DmaType.FLOOR)
                    elif action.tr_type.floor_type == FloorType.WALL:
                        row.append(DmaType.WALL)
                    elif action.tr_type.floor_type == FloorType.SECONDARY:
                        row.append(DmaType.WATER)
                    elif action.tr_type.floor_type == FloorType.FLOOR_OR_WALL:
                        row.append(DmaType.WALL)
                elif isinstance(action, EntityRule):
                    raise ValueError("Invalid rule type while rendering.")
                elif isinstance(action, DirectRule):
                    row.append(action.tile.terrain)
                ridx += 1
            row += [outside, outside, outside, outside, outside]
        rules.append([outside] * (self.fixed_floor.width + 10))
        rules.append([outside] * (self.fixed_floor.width + 10))
        rules.append([outside] * (self.fixed_floor.width + 10))
        rules.append([outside] * (self.fixed_floor.width + 10))
        rules.append([outside] * (self.fixed_floor.width + 10))

        dungeon = self.get_dungeon(rules)
        ctx.set_source_surface(dungeon, 0, 0)
        ctx.get_source().set_filter(cairo.Filter.NEAREST)
        ctx.paint()

        # Draw Pokémon, items, traps, etc.
        ridx = 0
        for y in range(0, self.fixed_floor.height):
            y += 5
            for x in range(0, self.fixed_floor.width):
                x += 5
                action = self.fixed_floor.actions[ridx]
                sx = DPC_TILING_DIM * DPCI_TILE_DIM * x
                sy = DPC_TILING_DIM * DPCI_TILE_DIM * y
                self._draw_action(ctx, action, sx, sy)
                ridx += 1

        obj = BytesIO()
        surface.write_to_png(obj)
        obj.seek(0)
        return obj

    def get_dungeon(self, rules: List[List[DmaType]]) -> cairo.Surface:
        dma_drawer = DmaDrawer(self.dma)
        mappings = dma_drawer.get_mappings_for_rules(rules, treat_outside_as_wall=True, variation_index=0)
        return pil_to_cairo_surface(
            dma_drawer.draw(mappings, self.dpci, self.dpc, self.dpl, None)[0].convert('RGBA')
        )

    def _draw_action(self, ctx, action, sx, sy):
        if isinstance(action, EntityRule):
            raise ValueError("Invalid rule type while rendering.")
        elif isinstance(action, TileRule):
            # Leader spawn tile
            if action.tr_type == TileRuleType.LEADER_SPAWN:
                raise ValueError("Invalid rule type while rendering.")
            # Attendant1 spawn tile
            if action.tr_type == TileRuleType.ATTENDANT1_SPAWN:
                raise ValueError("Invalid rule type while rendering.")
            # Attendant2 spawn tile
            if action.tr_type == TileRuleType.ATTENDANT2_SPAWN:
                raise ValueError("Invalid rule type while rendering.")
            # Attendant3 spawn tile
            if action.tr_type == TileRuleType.ATTENDANT3_SPAWN:
                raise ValueError("Invalid rule type while rendering.")
            # Key walls
            if action.tr_type == TileRuleType.FL_WA_ROOM_FLAG_0C or action.tr_type == TileRuleType.FL_WA_ROOM_FLAG_0D:
                sprite, x, y, w, h = self.sprite_provider.get_for_trap(31)
                ctx.translate(sx, sy)
                ctx.set_source_surface(sprite)
                ctx.get_source().set_filter(cairo.Filter.NEAREST)
                ctx.paint()
                ctx.translate(-sx, -sy)
            # Warp zone
            if action.tr_type == TileRuleType.WARP_ZONE or action.tr_type == TileRuleType.WARP_ZONE_2:
                if self.options.stairs:
                    self._draw_stairs(ctx, sx, sy)
        elif isinstance(action, DirectRule):
            if action.tile.room_type == RoomType.KECLEON_SHOP:
                if self.options.kecleon:
                    sprite, x, y, w, h = self.sprite_provider.get_for_trap(30)
                    ctx.translate(sx, sy)
                    ctx.set_source_surface(sprite)
                    ctx.get_source().set_filter(cairo.Filter.NEAREST)
                    ctx.paint()
                    ctx.translate(-sx, -sy)
            if action.tile.typ == TileType.PLAYER_SPAWN or action.tile.typ == TileType.ENEMY:
                if self.options.monsters:
                    self._draw_pokemon(ctx, action.itmtpmon_id, action.direction, sx, sy)
            if action.tile.typ == TileType.STAIRS:
                if self.options.stairs:
                    self._draw_stairs(ctx, sx, sy)
            if action.tile.typ == TileType.TRAP:
                if self.options.traps:
                    self._draw_trap(ctx, action.itmtpmon_id, sx, sy)
            if action.tile.typ == TileType.BURIED_ITEM:
                if self.options.burieditems:
                    self._draw_item(ctx, action.itmtpmon_id, sx, sy, buried=True)
            if action.tile.typ == TileType.ITEM:
                if self.options.flooritems:
                    self._draw_item(ctx, action.itmtpmon_id, sx, sy)

    def _draw_pokemon(self, ctx, md_idx, direction, sx, sy):
        sprite, cx, cy, w, h = self.sprite_provider.get_monster(md_idx, direction.ssa_id if direction is not None else 0)
        ctx.translate(sx, sy)
        ctx.set_source_surface(
            sprite,
            -cx + DPCI_TILE_DIM * DPC_TILING_DIM / 2,
            -cy + DPCI_TILE_DIM * DPC_TILING_DIM * 0.75
        )
        ctx.get_source().set_filter(cairo.Filter.NEAREST)
        ctx.paint()
        ctx.translate(-sx, -sy)

    def _draw_stairs(self, ctx, sx, sy):
        sprite, x, y, w, h = self.sprite_provider.get_for_trap(28)
        ctx.translate(sx, sy)
        ctx.set_source_surface(sprite)
        ctx.get_source().set_filter(cairo.Filter.NEAREST)
        ctx.paint()
        ctx.translate(-sx, -sy)

    def _draw_trap(self, ctx, trap_id, sx, sy):
        sprite, x, y, w, h = self.sprite_provider.get_for_trap(trap_id)
        ctx.translate(sx, sy)
        ctx.set_source_surface(sprite)
        ctx.paint()
        ctx.get_source().set_filter(cairo.Filter.NEAREST)
        ctx.translate(-sx, -sy)

    def _draw_item(self, ctx, item_id, sx, sy, buried=False):
        sprite, x, y, w, h = self.sprite_provider.get_for_item(item_id)
        ctx.translate(sx + 4, sy + 4)
        ctx.set_source_surface(sprite)
        ctx.get_source().set_filter(cairo.Filter.NEAREST)
        if buried:
            ctx.paint_with_alpha(0.5)
        else:
            ctx.paint()
        ctx.translate(-sx - 4, -sy - 4)


def pil_to_cairo_surface(im, format=cairo.FORMAT_ARGB32) -> cairo.ImageSurface:
    """
    :param im: Pillow Image
    :param format: Pixel format for output surface
    """
    assert format in (cairo.FORMAT_RGB24, cairo.FORMAT_ARGB32), "Unsupported pixel format: %s" % format
    arr = memoryview(bytearray(im.tobytes('raw', 'BGRa')))
    surface = cairo.ImageSurface.create_for_data(arr, format, im.width, im.height)
    return surface


class SpriteProvider:
    def __init__(self):
        with open(os.path.join(asset_path(), "dungeon.bin"), "rb") as f:
            self.dungeon_bin: DungeonBinPack = FileType.DUNGEON_BIN.deserialize(f.read(), static_data=STATIC_DATA)
        with open(os.path.join(asset_path(), "item_p.bin"), "rb") as f:
            self.item_p: ItemPProtocol = FileType.ITEM_P.deserialize(f.read())
        with open(os.path.join(asset_path(), "monster.md"), "rb") as f:
            self.monster_md: MdProtocol = FileType.MD.deserialize(f.read())
        with open(os.path.join(asset_path(), "monster.bin"), "rb") as f:
            self.monster_bin: BinPack = FileType.BIN_PACK.deserialize(f.read())

    def get_monster(self, md_index, direction_id: int):
        pil_img, cx, cy, w, h = self._retrieve_monster_sprite(md_index, direction_id)
        surf = pil_to_cairo_surface(pil_img)
        return surf, cx, cy, w, h

    def get_for_trap(self, trp: Union[MappaTrapType, int]):
        traps: ImgTrp = self.dungeon_bin.get(TRP_FILENAME)
        surf = pil_to_cairo_surface(traps.to_pil(trp, TRAP_PALETTE_MAP[trp]).convert('RGBA'))
        return surf, 0, 0, 24, 24

    def get_for_item(self, item_id):
        item = self.item_p.item_list[item_id]
        items: ImgItm = self.dungeon_bin.get(ITM_FILENAME)
        img = items.to_pil(item.sprite, item.palette)
        alpha = [px % 16 != 0 for px in img.getdata()]
        img = img.convert('RGBA')
        alphaimg = Image.new('1', (img.width, img.height))
        alphaimg.putdata(alpha)
        img.putalpha(alphaimg)
        surf = pil_to_cairo_surface(img)
        return surf, 0, 0, 16, 16

    def _retrieve_monster_sprite(self, md_index, direction_id: int) -> Tuple[Image.Image, int, int, int, int]:
        try:
            actor_sprite_id = self.monster_md[md_index].sprite_index
            if actor_sprite_id < 0:
                raise ValueError("Invalid Sprite index")
            sprite = self._load_sprite_from_bin_pack(self.monster_bin, actor_sprite_id)

            ani_group = sprite.anim_groups[0]
            frame_id = direction_id - 1 if direction_id > 0 else 0
            mfg_id = ani_group[frame_id].frames[0].frame_id

            sprite_img, (cx, cy) = sprite.render_frame(sprite.frames[mfg_id])
            return sprite_img, cx, cy, sprite_img.width, sprite_img.height
        except BaseException as e:
            raise RuntimeError(f"Error loading monster sprite for {md_index}") from e

    @staticmethod
    def _load_sprite_from_bin_pack(bin_pack: BinPack, file_id) -> Wan:
        return FileType.WAN.deserialize(FileType.COMMON_AT.deserialize(bin_pack[file_id]).decompress())


####################################


if __name__ == "__main__":
    # If this is run as a script, it will try to create the file structure for EOS_DUNGEONS_TILESET_PATH
    # at /tmp/dungeon_tiles and then exit. It will use the ROM at /tmp/rom.nds as a base for this.

    DUNGEON_BIN = 'DUNGEON/dungeon.bin'
    ITEM_BIN = 'BALANCE/item_p.bin'
    MONSTER_MD = 'BALANCE/monster.md'
    MONSTER_BIN = 'MONSTER/monster.bin'
    OUT_PATH = "/tmp/dungeon_tiles"
    NUMBER_OF_TILESETS = 170

    shutil.rmtree(OUT_PATH, ignore_errors=True)
    os.makedirs(OUT_PATH)
    rom = NintendoDSRom.fromFile("/tmp/rom.nds")

    # /dungeon.bin
    with open(os.path.join(OUT_PATH, "dungeon.bin"), "wb") as f:
        dungeon_bin_bytes = rom.getFileByName(DUNGEON_BIN)
        f.write(dungeon_bin_bytes)
        dungeon_bin = FileType.DUNGEON_BIN.deserialize(dungeon_bin_bytes, STATIC_DATA)

    # /base.dma
    with open(os.path.join(OUT_PATH, "base.dma"), "wb") as f:
        ok = False
        for i in range(0, len(dungeon_bin.get_files_bytes())):
            if "dungeon0.dma" == dungeon_bin.get_filename(i):
                f.write(dungeon_bin.get_files_bytes()[i])
                ok = True
                break
        assert ok

    # /base.dpc
    with open(os.path.join(OUT_PATH, "base.dpc"), "wb") as f:
        ok = False
        for i in range(0, len(dungeon_bin.get_files_bytes())):
            if "dungeon0.dpc" == dungeon_bin.get_filename(i):
                f.write(dungeon_bin.get_files_bytes()[i])
                ok = True
                break
        assert ok

    # /base.dpci
    with open(os.path.join(OUT_PATH, "base.dpci"), "wb") as f:
        ok = False
        for i in range(0, len(dungeon_bin.get_files_bytes())):
            if "dungeon0.dpci" == dungeon_bin.get_filename(i):
                f.write(dungeon_bin.get_files_bytes()[i])
                ok = True
                break
        assert ok

    # /base.dpl
    with open(os.path.join(OUT_PATH, "base.dpl"), "wb") as f:
        ok = False
        for i in range(0, len(dungeon_bin.get_files_bytes())):
            if "dungeon0.dpl" == dungeon_bin.get_filename(i):
                f.write(dungeon_bin.get_files_bytes()[i])
                ok = True
                break
        assert ok

    # /base.dpla
    with open(os.path.join(OUT_PATH, "base.dpla"), "wb") as f:
        ok = False
        for i in range(0, len(dungeon_bin.get_files_bytes())):
            if "dungeon0.dpla" == dungeon_bin.get_filename(i):
                f.write(dungeon_bin.get_files_bytes()[i])
                ok = True
                break
        assert ok

    # /item_p.bin
    with open(os.path.join(OUT_PATH, "item_p.bin"), "wb") as f:
        f.write(rom.getFileByName(ITEM_BIN))

    # /monster.md
    with open(os.path.join(OUT_PATH, "monster.md"), "wb") as f:
        f.write(rom.getFileByName(MONSTER_MD))

    # /monster.bin
    with open(os.path.join(OUT_PATH, "monster.bin"), "wb") as f:
        f.write(rom.getFileByName(MONSTER_BIN))

    # /dtef/x/
    for i in range(0, NUMBER_OF_TILESETS):
        fn = os.path.join(OUT_PATH, "dtef", str(i))
        os.makedirs(fn)
        dma = dungeon_bin.get(f'dungeon{i}.dma')
        dpc = dungeon_bin.get(f'dungeon{i}.dpc')
        dpci = dungeon_bin.get(f'dungeon{i}.dpci')
        dpl = dungeon_bin.get(f'dungeon{i}.dpl')
        dpla = dungeon_bin.get(f'dungeon{i}.dpla')

        dtef = ExplorersDtef(dma, dpc, dpci, dpl, dpla)

        # Write XML
        with open(os.path.join(fn, 'tileset.dtef.xml'), 'w') as f:
            f.write(ElementTree.tostring(dtef.get_xml(), encoding='unicode'))
        # Write Tiles
        var0, var1, var2, rest = dtef.get_tiles()
        var0fn, var1fn, var2fn, restfn = dtef.get_filenames()
        var0.save(os.path.join(fn, var0fn))
        var1.save(os.path.join(fn, var1fn))
        var2.save(os.path.join(fn, var2fn))
        rest.save(os.path.join(fn, restfn))
