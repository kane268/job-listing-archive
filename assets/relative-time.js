(() => {
  const DAY = 24 * 60 * 60 * 1000;
  const plural = (value, unit) => `${value} ${unit}${value === 1 ? '' : 's'}`;
  const targetDate = element => {
    const value = element.getAttribute('datetime') || '';
    const match = value.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (!match) return null;
    return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  };
  const relativeText = target => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    target.setHours(0, 0, 0, 0);
    const days = Math.round((target - today) / DAY);
    const past = days < 0;
    const abs = Math.abs(days);
    if (abs === 0) return 'today';
    if (abs === 1) return past ? 'yesterday' : 'tomorrow';
    if (abs < 14) return `${plural(abs, 'day')} ${past ? 'ago' : 'from now'}`;
    if (abs < 60) return `${plural(Math.round(abs / 7), 'week')} ${past ? 'ago' : 'from now'}`;
    if (abs < 730) return `${plural(Math.round(abs / 30), 'month')} ${past ? 'ago' : 'from now'}`;
    return `${plural(Math.round(abs / 365), 'year')} ${past ? 'ago' : 'from now'}`;
  };
  class ArchiveRelativeTime extends HTMLElement {
    connectedCallback() {
      const target = targetDate(this);
      if (!target) return;
      if (!this.title) this.title = target.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
      this.textContent = relativeText(target);
    }
  }
  if (!customElements.get('relative-time')) customElements.define('relative-time', ArchiveRelativeTime);
})();
