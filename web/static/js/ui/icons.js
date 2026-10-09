/** Inline SVG icon set. */
const ICONS = {
    menu: '<path d="M2 4h12M2 8h12M2 12h12"/>', search: '<circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5 14 14"/>',
    home: '<path d="M2 8 8 2.5 14 8M3.5 7v6.5h9V7"/>', asset: '<rect x="2.5" y="4" width="11" height="9" rx="1"/><path d="M5.5 4V2.5h5V4M2.5 8h11"/>',
    calc: '<rect x="3" y="1.8" width="10" height="12.4" rx="1"/><path d="M5.5 5h5M5.5 8h1M9.5 8h1M5.5 11h1M9.5 11h1"/>',
    calendar: '<rect x="2" y="3" width="12" height="11" rx="1"/><path d="M2 6.5h12M5 1.8v2.5M11 1.8v2.5"/>',
    journal: '<path d="M3.5 2h8.5a1 1 0 0 1 1 1v11H4.5a1 1 0 0 1-1-1zM3.5 13a1 1 0 0 1 1-1H13M6 5.5h4.5M6 8h4.5"/>',
    list: '<path d="M5.5 4h8M5.5 8h8M5.5 12h8M2.5 4h.5M2.5 8h.5M2.5 12h.5"/>', report: '<path d="M3 2h7l3 3v9H3zM10 2v3h3M5.5 8h5M5.5 10.5h5"/>',
    setup: '<circle cx="8" cy="8" r="2.2"/><path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M3.4 12.6l1.4-1.4M11.2 4.8l1.4-1.4"/>',
    plus: '<path d="M8 3v10M3 8h10"/>', monitor: '<rect x="2" y="2.5" width="12" height="8.5" rx="1"/><path d="M5.5 13.5h5M8 11v2.5"/>', chart: '<path d="M2.5 13.5h11M4.5 11V8M7.5 11V4.5M10.5 11V6.5"/>',
    pin: '<path d="M6 2.5h4M7 2.5v4L4.5 9h7L9 6.5v-4M8 9v4.5"/>', minus: '<path d="M3 8h10"/>',
    columns: '<rect x="2" y="2.5" width="12" height="11" rx="1"/><path d="M6.2 2.5v11M9.8 2.5v11"/>', group: '<path d="M2.5 3.5h5M4.5 3.5v9h6.5M4.5 8h6.5"/><circle cx="12.3" cy="8" r=".9"/><circle cx="12.3" cy="12.5" r=".9"/>', save: '<path d="M3 2.5h8l2.5 2.5v8.5h-10.5zM5.5 2.5v3.5h4.5V2.5M5.5 13.5V9.5h5v4"/>',
    trash: '<path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.5 9h6l.5-9"/>', edit: '<path d="M2.5 13.5l.6-3L11 2.6l2.4 2.4-7.9 7.9zM9.8 3.8l2.4 2.4"/>',
    refresh: '<path d="M13 8a5 5 0 1 1-1.6-3.7M13 2.5v3h-3"/>', transfer: '<path d="M2 5.5h11M10.5 3l2.5 2.5-2.5 2.5M14 10.5H3M5.5 8 3 10.5 5.5 13"/>',
    dispose: '<path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.5 9h6l.5-9M6.5 7.5l3 3M9.5 7.5l-3 3"/>', check: '<path d="M3 8.5 6.5 12 13 4.5"/>',
    x: '<path d="M3.5 3.5l9 9M12.5 3.5l-9 9"/>', chevron: '<path d="M6 3.5 10.5 8 6 12.5"/>', download: '<path d="M8 2v8M4.5 7 8 10.5 11.5 7M2.5 13.5h11"/>',
    print: '<path d="M4.5 6V2h7v4M4.5 11.5h-2v-5h11v5h-2M4.5 9.5h7v4h-7z"/>', attach: '<path d="M11.5 6.5 7 11a2 2 0 0 1-2.8-2.8l5-5a3 3 0 0 1 4.3 4.2l-5.2 5.2"/>',
    moon: '<path d="M13 9.5A5.5 5.5 0 0 1 6.5 3a5.5 5.5 0 1 0 6.5 6.5z"/>', sun: '<circle cx="8" cy="8" r="3"/><path d="M8 1.5v1.8M8 12.7v1.8M1.5 8h1.8M12.7 8h1.8M3.4 3.4l1.3 1.3M11.3 11.3l1.3 1.3M3.4 12.6l1.3-1.3M11.3 4.7l1.3-1.3"/>',
    wrench: '<path d="M10.5 2.5a3.3 3.3 0 0 0-3.1 4.4L2.5 11.8a1.4 1.4 0 0 0 2 2l4.9-4.9a3.3 3.3 0 0 0 4.4-3.1l-2 1.6-1.8-.4-.4-1.8z"/>',
    truck: '<path d="M1.5 4h8v7h-8zM9.5 6.5h3l2 2V11h-5zM4.5 13a1.3 1.3 0 1 0 0-.01zM11.5 13a1.3 1.3 0 1 0 0-.01z"/>',
    db: '<ellipse cx="8" cy="4" rx="5" ry="2"/><path d="M3 4v8c0 1.1 2.2 2 5 2s5-.9 5-2V4M3 8c0 1.1 2.2 2 5 2s5-.9 5-2"/>',
    user: '<circle cx="8" cy="5.2" r="2.6"/><path d="M2.8 14c.4-3 2.5-4.6 5.2-4.6s4.8 1.6 5.2 4.6"/>',
    eye: '<path d="M1.5 8s2.3-4.5 6.5-4.5S14.5 8 14.5 8s-2.3 4.5-6.5 4.5S1.5 8 1.5 8z"/><circle cx="8" cy="8" r="2"/>', eyeoff: '<path d="M2 2l12 12M6.4 4.1A6.6 6.6 0 0 1 8 3.5c4.2 0 6.5 4.5 6.5 4.5a11 11 0 0 1-2 2.5M4 5.5C2.5 6.7 1.5 8 1.5 8s2.3 4.5 6.5 4.5c1 0 1.9-.3 2.6-.6M6.6 6.6a2 2 0 0 0 2.8 2.8"/>',
    logout: '<path d="M6.5 2.5h-3v11h3M10 5l3 3-3 3M13 8H6"/>', key: '<circle cx="5.5" cy="10.5" r="2.5"/><path d="M7.3 8.7 13 3M11 5l1.5 1.5M9.5 6.5 11 8"/>',
    globe: '<circle cx="8" cy="8" r="6"/><path d="M2 8h12M8 2c2 2 2 10 0 12M8 2c-2 2-2 10 0 12"/>', back: '<path d="M9.5 3 4.5 8l5 5M4.5 8h9"/>',
    lock: '<rect x="3.5" y="7" width="9" height="6.5" rx="1"/><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2"/>', unlock: '<rect x="3.5" y="7" width="9" height="6.5" rx="1"/><path d="M5.5 7V5a2.5 2.5 0 0 1 4.8-1"/>',
    play: '<path d="M4.5 2.5v11l9-5.5z"/>', filter: '<path d="M2 3h12l-4.5 5.5V13l-3-1.5V8.5z"/>', audit: '<circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5 14 14M5 7l1.5 1.5L9 5.5"/>',
    warn: '<path d="M8 2 14.5 13.5h-13zM8 6.5v3.2M8 11.6v.4"/>', copy: '<rect x="5.5" y="5.5" width="8" height="8" rx="1"/><path d="M10.5 5.5v-2a1 1 0 0 0-1-1h-6a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2"/>',
};
export function icon(name) {
    const s = document.createElement("span");
    s.style.display = "inline-flex";
    s.innerHTML = `<svg class="ic" viewBox="0 0 16 16" aria-hidden="true">${ICONS[name] || ""}</svg>`;
    return s;
}
