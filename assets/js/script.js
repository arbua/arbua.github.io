'use strict';

const elementToggleFunc = function (elem) { elem.classList.toggle('active'); };

function initSidebar() {
  const sidebar = document.querySelector('[data-sidebar]');
  const sidebarBtn = document.querySelector('[data-sidebar-btn]');
  if (!sidebar || !sidebarBtn) return;

  sidebarBtn.addEventListener('click', function () {
    elementToggleFunc(sidebar);
  });
}

function initTestimonialsModal() {
  const testimonialsItems = document.querySelectorAll('[data-testimonials-item]');
  const modalContainer = document.querySelector('[data-modal-container]');
  const modalCloseBtn = document.querySelector('[data-modal-close-btn]');
  const overlay = document.querySelector('[data-overlay]');
  const modalTitle = document.querySelector('[data-modal-title]');
  const modalText = document.querySelector('[data-modal-text]');
  const modalImg = document.querySelector('[data-modal-img]');
  const modalTime = document.querySelector('.testimonials-modal time');

  if (!testimonialsItems.length || !modalContainer || !modalCloseBtn || !overlay || !modalTitle || !modalText || !modalImg || !modalTime) {
    return;
  }

  const openModal = (item) => {
    const title = item.querySelector('[data-testimonials-title]')?.textContent || '';
    const text = item.querySelector('[data-testimonials-text] p')?.innerHTML || '';
    const avatar = item.querySelector('[data-testimonials-avatar]')?.src || '';
    const timeElem = item.querySelector('time');

    const dateValue = timeElem ? timeElem.getAttribute('datetime') : '2025-01-01';
    const formattedDate = timeElem ? timeElem.textContent : '1 January, 2025';

    modalTitle.textContent = title;
    modalText.innerHTML = `<p>${text}</p>`;
    modalImg.src = avatar;
    modalImg.alt = title;
    modalTime.setAttribute('datetime', dateValue || '2025-01-01');
    modalTime.textContent = formattedDate || '1 January, 2025';

    modalContainer.classList.add('active');
    overlay.classList.add('active');
  };

  const closeModal = () => {
    modalContainer.classList.remove('active');
    overlay.classList.remove('active');
  };

  testimonialsItems.forEach((item) => {
    item.addEventListener('click', () => openModal(item));
  });

  modalCloseBtn.addEventListener('click', closeModal);
  overlay.addEventListener('click', closeModal);
}

function initPublicationFilter() {
  const select = document.querySelector('[data-select]');
  const selectItems = document.querySelectorAll('[data-select-item]');
  const selectValue = document.querySelector('[data-selecct-value]');
  const filterButtons = document.querySelectorAll('[data-filter-btn]');
  const filterItems = document.querySelectorAll('[data-filter-item]');
  const searchInput = document.querySelector('[data-publication-search]');
  const publicationCount = document.querySelector('[data-publication-count]');
  const publicationEmpty = document.querySelector('[data-publication-empty]');

  if (!select || !selectValue || !filterButtons.length || !filterItems.length) return;

  let selectedCategory = 'all';
  let searchQuery = '';

  const applyFilters = function () {
    let visibleCount = 0;
    for (let i = 0; i < filterItems.length; i++) {
      const category = (filterItems[i].dataset.category || '').toLowerCase();
      const title = filterItems[i].querySelector('.project-title')?.textContent.toLowerCase() || '';
      const summary = filterItems[i].querySelector('.project-summary')?.textContent.toLowerCase() || '';
      const searchableText = `${title} ${summary}`;

      const matchesCategory = selectedCategory === 'all' || selectedCategory === category;
      const matchesSearch = !searchQuery || searchableText.includes(searchQuery);

      const isVisible = matchesCategory && matchesSearch;
      filterItems[i].classList.toggle('active', isVisible);
      if (isVisible) visibleCount += 1;
    }

    if (publicationCount) {
      publicationCount.textContent = `${visibleCount} publication${visibleCount === 1 ? '' : 's'} shown`;
    }

    if (publicationEmpty) {
      publicationEmpty.hidden = visibleCount !== 0;
    }
  };

  select.addEventListener('click', function () {
    elementToggleFunc(this);
  });

  for (let i = 0; i < selectItems.length; i++) {
    selectItems[i].addEventListener('click', function () {
      selectedCategory = this.innerText.toLowerCase();
      selectValue.innerText = this.innerText;
      elementToggleFunc(select);
      applyFilters();
    });
  }

  let lastClickedBtn = filterButtons[0];
  for (let i = 0; i < filterButtons.length; i++) {
    filterButtons[i].addEventListener('click', function () {
      selectedCategory = this.innerText.toLowerCase();
      selectValue.innerText = this.innerText;
      applyFilters();

      if (lastClickedBtn) lastClickedBtn.classList.remove('active');
      this.classList.add('active');
      lastClickedBtn = this;
    });
  }

  if (searchInput) {
    searchInput.addEventListener('input', function () {
      searchQuery = this.value.trim().toLowerCase();
      applyFilters();
    });
  }

  applyFilters();
}

function initContactForm() {
  const form = document.querySelector('[data-form]');
  const formInputs = document.querySelectorAll('[data-form-input]');
  const formBtn = document.querySelector('[data-form-btn]');
  const formStatus = document.querySelector('[data-form-status]');

  if (!form || !formBtn) return;

  for (let i = 0; i < formInputs.length; i++) {
    formInputs[i].addEventListener('input', function () {
      if (form.checkValidity()) {
        formBtn.removeAttribute('disabled');
      } else {
        formBtn.setAttribute('disabled', '');
      }
    });
  }

  form.addEventListener('submit', async function (event) {
    event.preventDefault();
    if (!form.checkValidity()) return;

    const formButtonLabel = formBtn.querySelector('span');
    const originalLabel = formButtonLabel ? formButtonLabel.textContent : 'Send Message';
    const endpoint = form.dataset.formEndpoint || 'https://formsubmit.co/ajax/larboit@unistra.fr';
    const formData = new FormData(form);

    const payload = {
      name: (formData.get('fullname') || '').toString(),
      email: (formData.get('email') || '').toString(),
      message: (formData.get('message') || '').toString(),
      _subject: (formData.get('_subject') || 'Website contact form message').toString(),
      _template: (formData.get('_template') || 'table').toString(),
      _captcha: (formData.get('_captcha') || 'false').toString(),
      _honey: (formData.get('_honey') || '').toString()
    };

    formBtn.setAttribute('disabled', '');
    if (formButtonLabel) formButtonLabel.textContent = 'Sending...';
    if (formStatus) {
      formStatus.textContent = 'Sending your message...';
      formStatus.style.color = '#f4b400';
    }

    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json'
        },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        throw new Error(`Request failed: ${response.status}`);
      }

      form.reset();
      formBtn.setAttribute('disabled', '');

      if (formStatus) {
        formStatus.textContent = 'Message sent successfully. Thank you!';
        formStatus.style.color = '#45e28a';
      }
    } catch (error) {
      if (formStatus) {
        formStatus.textContent = 'Unable to send right now. Please try again in a moment.';
        formStatus.style.color = '#ff6b6b';
      }
    } finally {
      if (formButtonLabel) formButtonLabel.textContent = originalLabel;
    }
  });
}

function initPageNavigation() {
  const navigationLinks = document.querySelectorAll('[data-nav-link]');
  const pages = document.querySelectorAll('[data-page]');
  if (!navigationLinks.length || !pages.length) return;

  for (let i = 0; i < navigationLinks.length; i++) {
    navigationLinks[i].addEventListener('click', function () {
      const selectedPage = this.innerHTML.toLowerCase();

      for (let j = 0; j < pages.length; j++) {
        if (selectedPage === pages[j].dataset.page) {
          pages[j].classList.add('active');
          navigationLinks[j].classList.add('active');
          window.scrollTo(0, 0);
        } else {
          pages[j].classList.remove('active');
          navigationLinks[j].classList.remove('active');
        }
      }
    });
  }
}

function initPublicationToggles() {
  document.querySelectorAll('.publication-trigger').forEach(function (trigger, index) {
    const summary = trigger.parentElement.querySelector('.project-summary');
    if (summary) {
      const summaryId = summary.id || `publication-summary-${index}`;
      summary.id = summaryId;
      summary.hidden = summary.style.display !== 'block';
      trigger.setAttribute('role', 'button');
      trigger.setAttribute('aria-controls', summaryId);
      trigger.setAttribute('aria-expanded', 'false');
    }

    trigger.addEventListener('click', function (event) {
      event.preventDefault();
      const summary = this.parentElement.querySelector('.project-summary');
      if (summary) {
        const shouldExpand = summary.style.display !== 'block';
        summary.style.display = shouldExpand ? 'block' : 'none';
        summary.hidden = !shouldExpand;
        this.setAttribute('aria-expanded', shouldExpand ? 'true' : 'false');
      }
    });
  });
}

function initSite() {
  initSidebar();
  initTestimonialsModal();
  initPublicationFilter();
  initContactForm();
  initPageNavigation();
  initPublicationToggles();
}

let siteInitialized = false;

async function initializeWhenReady() {
  if (siteInitialized) return;

  if (window.partialsReady && typeof window.partialsReady.then === 'function') {
    await window.partialsReady;
  }

  if (siteInitialized) return;
  initSite();
  siteInitialized = true;
}

document.addEventListener('DOMContentLoaded', initializeWhenReady);
document.addEventListener('partials:loaded', initializeWhenReady);
