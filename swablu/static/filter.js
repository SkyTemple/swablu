/** @type {HTMLInputElement} */
var inpName = document.querySelector('#filter-form [name=name]');
/** @type {HTMLSelectElement} */
var selType = document.querySelector('#filter-form [name=type]');
/** @type {HTMLSelectElement} */
var selStatus = document.querySelector('#filter-form [name=status]');
/** @type {HTMLSelectElement} */
var selSort = document.querySelector('#filter-form [name=sort]');
/** @type {HTMLSelectElement} */
var selView = document.querySelector('#filter-form [name=view]');

function _keep(a, b) {
    var i, item;
    for (i = a.length - 1; i >= 0; i -= 1) {
        item = a[i];
        if (!b.includes(item)) {
            a.splice(i, 1);
        }
    }
}

function refilter() {
    // this is garbage.
    var hack_types = [
        'balance_hack_wip', 'balance_hack_mostly', 'balance_hack',
        'story_hack_wip', 'story_hack_mostly', 'story_hack',
        'translation_wip', 'translation_mostly', 'translation',
        'misc_hack_wip', 'misc_hack_mostly', 'misc_hack',
        'machinima_ongoing', 'machinima'
    ];
    
    switch (selStatus.value) {
        case "wip":
            _keep(hack_types, ['balance_hack_wip', 'story_hack_wip', 'translation_wip', 'misc_hack_wip']);
            break;
        case "mostly":
            _keep(hack_types, ['balance_hack_mostly', 'story_hack_mostly', 'translation_mostly', 'misc_hack_mostly', 'machinima_ongoing']);
            break;
        case "finished":
            _keep(hack_types, ['balance_hack', 'story_hack', 'translation', 'misc_hack', 'machinima']);
            break;
    }
    
    switch (selType.value) {
        case "balance_hack":
            _keep(hack_types, ['balance_hack_wip', 'balance_hack_mostly', 'balance_hack']);
            break;
        case "story_hack":
            _keep(hack_types, ['story_hack_wip', 'story_hack_mostly', 'story_hack']);
            break;
        case "translation":
            _keep(hack_types, ['translation_wip', 'translation_mostly', 'translation']);
            break;
        case "misc_hack":
            _keep(hack_types, ['misc_hack_wip', 'misc_hack_mostly', 'misc_hack']);
            break;
        case "machinima":
            _keep(hack_types, ['machinima_ongoing', 'machinima']);
            break;
    }
    var name = inpName.value.trim().toLowerCase();

    var list = document.querySelector('.hack-list');
    while (list.lastElementChild) {
        list.removeChild(list.lastElementChild);
    }
    var containerToAddTo = list;
    if (selSort.value === 'abc') {
        containerToAddTo = [];
        containerToAddTo.append = containerToAddTo.push;
    }
    if (selView.value === 'compact') {
        list.classList.add('mode-compact');
    } else {
        list.classList.remove('mode-compact');
    }
    document.querySelectorAll('.tmpl-hack-list .hack-content').forEach(function (div) {
        var shouldShow = true;
        if (name !== "") {
            shouldShow = div.getAttribute('data-name').toLowerCase().includes(name);
        }
        shouldShow &&= hack_types.includes(div.getAttribute('data-type'));
        if (shouldShow) {
            containerToAddTo.append(div.cloneNode(true));
        }
    })
    if (selSort.value === 'abc') {
        containerToAddTo
            .sort(function(a, b) {return a.getAttribute('data-name') < b.getAttribute('data-name') ? -1 : 1;})
            .forEach(function(ele) {list.append(ele);});
    }
    document.querySelector('.error').style.display = 'none';
}

inpName.oninput = refilter
selType.onchange = refilter
selStatus.onchange = refilter
selSort.onchange = refilter
selView.onchange = refilter
refilter();