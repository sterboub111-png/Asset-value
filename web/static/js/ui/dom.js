/** DOM helper: `h()` builds elements, `append`, `clear`. */
export function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
        if (v === undefined || v === null || v === false)
            continue;
        if (k === "class")
            el.className = v;
        else if (k.startsWith("on") && typeof v === "function")
            el.addEventListener(k.slice(2), v);
        else if (k === "value")
            el.value = v;
        else if (v === true)
            el.setAttribute(k, "");
        else
            el.setAttribute(k, String(v));
    }
    append(el, kids);
    return el;
}
export function append(el, kids) {
    for (const k of kids.flat(Infinity)) {
        if (k === null || k === undefined || k === false)
            continue;
        el.appendChild(k instanceof Node ? k : document.createTextNode(String(k)));
    }
}
export const clear = (el) => { while (el.firstChild)
    el.removeChild(el.firstChild); };
