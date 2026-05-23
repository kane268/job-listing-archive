(() => {
  const filterInput = document.getElementById('listing-filter-input');
  if (filterInput) {
    const cards = Array.from(document.querySelectorAll('.listing-card'));
    const applyFilter = () => {
      const query = filterInput.value.trim().toLowerCase();
      for (const card of cards) {
        const haystack = (card.dataset.search || card.textContent || '').toLowerCase();
        card.hidden = query !== '' && !haystack.includes(query);
      }
    };
    filterInput.addEventListener('input', applyFilter);
    applyFilter();
  }
})();
