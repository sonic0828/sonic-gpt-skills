// Optional page structures share the catalog search, selection and evidence view.
let drawer, sidebarToggle, sceneIndex = 0, sceneItems = [];

function setupStructure() {
  const inventory = document.querySelector(".inventory");
  if (structure === "02" || structure === "03") {
    const sidebar = el("aside",undefined,"sidebar");
    inventory.before(sidebar);
    sidebarToggle = el("button","浏览目录","sidebar-toggle");
    sidebarToggle.setAttribute("aria-expanded","false");
    sidebarToggle.setAttribute("aria-controls","directory");
    const directory = el("div");
    directory.id = "directory";
    sidebarToggle.onclick = () => {
      const open = sidebarToggle.getAttribute("aria-expanded") === "true";
      sidebarToggle.setAttribute("aria-expanded",String(!open));
    };
    if (structure === "02") directory.append(document.querySelector("nav"));
    if (groups.length) {
      const sub = el("div");
      sub.id = "subcategories";
      directory.append(sub);
    }
    sidebar.append(sidebarToggle,directory);
    directory.append(inventory);
  }
  if (structure === "04") {
    drawer = el("dialog",undefined,"drawer");
    drawer.setAttribute("aria-label","资产详情");
    const close = el("button","关闭详情","drawer-close");
    close.onclick = () => drawer.close();
    drawer.append(close,$("detail"));
    document.body.append(drawer);
    drawer.onclose = () => {
      drawer.querySelectorAll("audio,video").forEach(player => player.pause());
      if (location.hash) history.replaceState(null,"",location.href.split("#")[0]);
    };
  }
  if (structure === "06") {
    const section = el("section",undefined,"scene-view");
    section.id = "scene-view";
    inventory.before(section);
  }
}

function appendScopeFilters(ordered) {
  for (const name of [null,...groups.map(([name]) => name)]) {
    const button = el("button",name || "全部资产","filter");
    button.setAttribute("aria-pressed",String(scope === name));
    button.onclick = () => { scope = name; category = null; filters(); list(); };
    $("filters").append(button);
  }
  const select = el("select",undefined,"more");
  select.setAttribute("aria-label","范围内分类");
  select.add(new Option("全部分类",""));
  for (const c of ordered.filter(c => !scope || scopeCategories().includes(c))) {
    select.add(new Option(c,c));
  }
  select.value = category || "";
  select.onchange = () => { category = select.value || null; list(); };
  $("subcategories").append(select);
}

function openDrawer() {
  if (!drawer.open) drawer.showModal();
  drawer.scrollTop = 0;
}

function sceneFor(item) {
  const contains = scene => item?.sources.some(ref => ref.rect && ref.path === scene.path);
  if (contains(view.scenes[sceneIndex])) return sceneIndex;
  const index = view.scenes.findIndex(contains);
  return index < 0 ? sceneIndex : index;
}

function showSelection(item) {
  if (drawer) { openDrawer(); return; }
  if (sidebarToggle) sidebarToggle.setAttribute("aria-expanded","false");
  if (structure === "06") {
    const index = sceneFor(item);
    if (index !== sceneIndex) { sceneIndex = index; renderScene(sceneItems); }
  }
  if (matchMedia("(max-width:760px)").matches || structure === "05") {
    $("detail").scrollIntoView({block:"nearest"});
  }
}

function renderTable(visible) {
  const table = el("table",undefined,"asset-table");
  table.setAttribute("aria-label","资产属性");
  const available = new Set(visible.flatMap(i => Object.keys(i.attributes || {})));
  const keys = view.columns?.length ? view.columns.filter(k => available.has(k)) : [...available];
  const hasUses = visible.some(i => i.uses?.length);
  const audioRef = i => i.sources.find(s => s.preview && files[s.path] && mediaType(s.path) === "audio");
  const hasAudio = visible.some(audioRef);
  const headings = ["对象","分类",...keys];
  if (hasUses) headings.push("使用场景");
  if (hasAudio) headings.push("试听");
  const row = table.createTHead().insertRow();
  for (const title of headings) {
    const th = el("th",title); th.scope = "col"; row.append(th);
  }
  const body = table.createTBody();
  for (const item of visible) {
    const row = body.insertRow();
    const button = el("button",assetName(item),"row-name");
    button.dataset.itemId = item.id;
    button.setAttribute("aria-current",String(item.id === selected));
    button.onclick = () => choose(item);
    row.insertCell().append(button);
    row.insertCell().textContent = item.category;
    for (const key of keys) row.insertCell().textContent = item.attributes?.[key] ?? "—";
    if (hasUses) row.insertCell().textContent = [...new Set((item.uses || []).map(u => u.scene))].join("、") || "—";
    if (hasAudio) {
      const cell = row.insertCell(), ref = audioRef(item);
      if (ref) {
        const player = el("audio"); player.controls = true; player.preload = "none";
        player.src = url(ref.path); player.setAttribute("aria-label","试听 " + assetName(item));
        cell.append(player);
      }
    }
  }
  $("cards").append(table);
}

function renderScene(visible) {
  sceneItems = visible;
  const section = $("scene-view"), scene = view.scenes[sceneIndex];
  section.replaceChildren();
  if (view.scenes.length > 1) {
    const select = el("select",undefined,"more");
    select.setAttribute("aria-label","场景画面");
    view.scenes.forEach((s,i) => select.add(new Option(s.name,String(i))));
    select.value = String(sceneIndex);
    select.onchange = () => {
      sceneIndex = Number(select.value);
      renderScene(visible);
      const first = visible.find(i => i.status !== "removed" && i.sources.some(
        s => s.rect && s.path === view.scenes[sceneIndex].path));
      if (first) choose(first);
    };
    section.append(select);
  } else section.append(el("h2",scene.name));
  const regions = visible.filter(i => i.status !== "removed").flatMap(item => item.sources
    .filter(ref => ref.path === scene.path && ref.rect).map(ref => ({item,rect:ref.rect})));
  if (!regions.length || !files[scene.path]) {
    section.append(el("p","当前范围没有可定位的区域，可从对象目录查看来源。","empty"));
    return;
  }
  const stage = el("div",undefined,"scene-stage"), frame = el("div",undefined,"scene-frame"), img = new Image();
  img.alt = scene.name;
  img.onload = () => {
    for (const {item,rect:[x,y,w,h]} of regions) {
      if (x+w > img.naturalWidth || y+h > img.naturalHeight) continue;
      const pin = el("button",undefined,"hotspot");
      pin.title = assetName(item); pin.setAttribute("aria-label",assetName(item));
      pin.dataset.itemId = item.id;
      pin.setAttribute("aria-current",String(item.id === selected));
      Object.assign(pin.style,{left:x/img.naturalWidth*100+"%", top:y/img.naturalHeight*100+"%",
        width:w/img.naturalWidth*100+"%", height:h/img.naturalHeight*100+"%"});
      pin.onclick = () => choose(item);
      frame.append(pin);
    }
  };
  img.onerror = () => stage.replaceChildren(el("p","场景图未载入，可使用对象目录。","error"));
  frame.append(img); stage.append(frame); section.append(stage); img.src = url(scene.path);
}
