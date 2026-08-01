(() => {
  const sidebar = document.querySelector('.sidebar');
  const toggle = document.querySelector('.mobile-toggle');
  const links = [...document.querySelectorAll('.nav-list a')];
  const sections = links.map(link => document.querySelector(link.hash)).filter(Boolean);

  toggle?.addEventListener('click', () => {
    const open = sidebar.classList.toggle('open');
    toggle.setAttribute('aria-expanded', String(open));
  });
  links.forEach(link => link.addEventListener('click', () => sidebar.classList.remove('open')));

  const observer = new IntersectionObserver(entries => {
    const visible = entries.filter(entry => entry.isIntersecting)
      .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
    if (!visible) return;
    links.forEach(link => link.classList.toggle('active', link.hash === `#${visible.target.id}`));
  }, { rootMargin: '-20% 0px -65%', threshold: [0, .2, .6] });
  sections.forEach(section => observer.observe(section));
})();
