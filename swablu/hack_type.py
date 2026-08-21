def get_hack_type_str(hack_type):
    if hack_type == "balance_hack_wip":
        return "Balance Hack (work in progress)"
    if hack_type == "balance_hack_mostly":
        return "Balance Hack (mostly finished)"
    if hack_type == "balance_hack":
        return "Balance Hack (finished)"
    if hack_type == "gameplay_hack_wip":
        return "Gameplay Hack (work in progress)"
    if hack_type == "gameplay_hack_mostly":
        return "Gameplay Hack (mostly finished)"
    if hack_type == "gameplay_hack":
        return "Gameplay Hack (finished)"
    if hack_type == "story_hack_wip":
        return "Story Hack (work in progress)"
    if hack_type == "story_hack_mostly":
        return "Story Hack (mostly finished)"
    if hack_type == "story_hack":
        return "Story Hack (finished)"
    if hack_type == "translation_wip":
        return "Translation (work in progress)"
    if hack_type == "translation_mostly":
        return "Translation (mostly finished)"
    if hack_type == "translation":
        return "Translation (finished)"
    if hack_type == "misc_hack_wip":
        return "Misc. Hack (work in progress)"
    if hack_type == "misc_hack_mostly":
        return "Misc. Hack (mostly finished)"
    if hack_type == "misc_hack":
        return "Misc. Hack (finished)"
    if hack_type == "machinima_ongoing":
        return "Machinima (ongoing)"
    if hack_type == "machinima":
        return "Machinima (finished)"
    return "Misc. Hack"
