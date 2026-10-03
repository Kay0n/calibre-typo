// The search box is hidden unless this script runs
for (const picker of document.querySelectorAll(".book-picker")) {
  const search = picker.querySelector("input");
  const select = picker.querySelector("select");
  // Rebuilt rather than hidden: Safari ignores hidden options
  const groups = [...select.querySelectorAll("optgroup")].map((group) => ({
    label: group.label,
    options: [...group.querySelectorAll("option")],
  }));

  search.hidden = false;
  search.addEventListener("input", () => {
    const words = search.value.toLowerCase().split(/\s+/).filter(Boolean);
    const chosen = select.value;
    select.replaceChildren(...groups.flatMap(({ label, options }) => {
      const matches = options.filter((o) => words.every((w) => o.text.toLowerCase().includes(w)));
      if (!matches.length) return [];
      const group = document.createElement("optgroup");
      group.label = label;
      group.append(...matches);
      return [group];
    }));
    select.value = chosen;
  });
  search.addEventListener("keydown", (event) => {
    if (event.key === "Enter") event.preventDefault(); // would submit the whole form
    if (event.key === "ArrowDown" && select.options.length) {
      event.preventDefault();
      if (select.selectedIndex < 0) select.selectedIndex = 0;
      select.focus();
    }
  });
}
