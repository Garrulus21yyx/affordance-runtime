(() => {
  const toggle = document.querySelector(".nav-toggle");
  const nav = document.querySelector(".top-nav");
  if (toggle && nav) {
    toggle.addEventListener("click", () => {
      const open = nav.classList.toggle("open");
      toggle.setAttribute("aria-expanded", String(open));
    });
  }

  const sections = [...document.querySelectorAll("main section[id], .qa-group[id]")];
  const sideLinks = [...document.querySelectorAll(".side-nav a[href^='#']")];
  if (sections.length && sideLinks.length && "IntersectionObserver" in window) {
    const linkById = new Map(sideLinks.map((link) => [link.getAttribute("href").slice(1), link]));
    const observer = new IntersectionObserver((entries) => {
      const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (!visible) return;
      sideLinks.forEach((link) => link.classList.remove("active"));
      linkById.get(visible.target.id)?.classList.add("active");
    }, { rootMargin: "-18% 0px -68%", threshold: [0.01, 0.2] });
    sections.forEach((section) => observer.observe(section));
  }

  document.querySelectorAll(".harness").forEach((harness) => {
    const buttons = [...harness.querySelectorAll(".owner-filter")];
    const steps = [...harness.querySelectorAll(".rail-step")];
    buttons.forEach((button) => button.addEventListener("click", () => {
      const owner = button.dataset.owner || "all";
      buttons.forEach((item) => item.classList.toggle("active", item === button));
      steps.forEach((step) => {
        const owners = (step.dataset.owner || "").split(" ");
        const match = owner === "all" || owners.includes(owner);
        step.classList.toggle("dimmed", !match);
        step.classList.toggle("highlight", match && owner !== "all");
      });
    }));
  });

  const search = document.querySelector("[data-qa-search]");
  const count = document.querySelector("[data-qa-count]");
  const questions = [...document.querySelectorAll("details.qa")];
  if (search && questions.length) {
    const update = () => {
      const query = search.value.trim().toLocaleLowerCase("zh-CN");
      let visible = 0;
      questions.forEach((item) => {
        const match = !query || item.textContent.toLocaleLowerCase("zh-CN").includes(query);
        item.classList.toggle("hidden", !match);
        if (match) visible += 1;
      });
      document.querySelectorAll(".qa-group").forEach((group) => {
        const hasVisible = group.querySelector("details.qa:not(.hidden)");
        group.hidden = Boolean(query) && !hasVisible;
      });
      if (count) count.textContent = `${visible} / ${questions.length}`;
    };
    search.addEventListener("input", update);
    update();
  }
})();
