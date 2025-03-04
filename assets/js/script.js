'use strict';



// element toggle function
const elementToggleFunc = function (elem) { elem.classList.toggle("active"); }



// sidebar variables
const sidebar = document.querySelector("[data-sidebar]");
const sidebarBtn = document.querySelector("[data-sidebar-btn]");

// sidebar toggle functionality for mobile
sidebarBtn.addEventListener("click", function () { elementToggleFunc(sidebar); });



// testimonials variables
// Select testimonials items and modal elements
const testimonialsItem = document.querySelectorAll("[data-testimonials-item]");
const modalContainer = document.querySelector("[data-modal-container]");
const modalCloseBtn = document.querySelector("[data-modal-close-btn]");
const overlay = document.querySelector("[data-overlay]");
const modalTitle = document.querySelector("[data-modal-title]");
const modalText = document.querySelector("[data-modal-text]");
const modalImg = document.querySelector("[data-modal-img]");
const modalTime = document.querySelector(".testimonials-modal time"); // Selects the <time> in the modal

// Function to open modal
const openModal = (item) => {
  // Extract content from clicked testimonial
  const title = item.querySelector("[data-testimonials-title]").textContent;
  const text = item.querySelector("[data-testimonials-text] p").innerHTML;
  const avatar = item.querySelector("[data-testimonials-avatar]").src;
  const timeElem = item.querySelector("time"); // Select the hidden time element

  const dateValue = timeElem ? timeElem.getAttribute("datetime") : "2025-01-01";
  const formattedDate = timeElem ? timeElem.textContent : "1 January, 2025";

  // Update modal content
  modalTitle.textContent = title;
  modalText.innerHTML = `<p>${text}</p>`;
  modalImg.src = avatar;
  modalImg.alt = title;
  modalTime.setAttribute("datetime", dateValue);
  modalTime.textContent = formattedDate;

  // Show modal and overlay
  modalContainer.classList.add("active");
  overlay.classList.add("active");
};

// Function to close modal
const closeModal = () => {
  modalContainer.classList.remove("active");
  overlay.classList.remove("active");
};

// Add click event to each testimonial item
testimonialsItem.forEach(item => {
  item.addEventListener("click", () => openModal(item));
});

// Close modal when clicking close button or overlay
modalCloseBtn.addEventListener("click", closeModal);
overlay.addEventListener("click", closeModal);


// custom select variables
const select = document.querySelector("[data-select]");
const selectItems = document.querySelectorAll("[data-select-item]");
const selectValue = document.querySelector("[data-selecct-value]");
const filterBtn = document.querySelectorAll("[data-filter-btn]");

select.addEventListener("click", function () { elementToggleFunc(this); });

// add event in all select items
for (let i = 0; i < selectItems.length; i++) {
  selectItems[i].addEventListener("click", function () {

    let selectedValue = this.innerText.toLowerCase();
    selectValue.innerText = this.innerText;
    elementToggleFunc(select);
    filterFunc(selectedValue);

  });
}

// filter variables
const filterItems = document.querySelectorAll("[data-filter-item]");

const filterFunc = function (selectedValue) {

  for (let i = 0; i < filterItems.length; i++) {

    if (selectedValue === "all") {
      filterItems[i].classList.add("active");
    } else if (selectedValue === filterItems[i].dataset.category) {
      filterItems[i].classList.add("active");
    } else {
      filterItems[i].classList.remove("active");
    }

  }

}

// add event in all filter button items for large screen
let lastClickedBtn = filterBtn[0];

for (let i = 0; i < filterBtn.length; i++) {

  filterBtn[i].addEventListener("click", function () {

    let selectedValue = this.innerText.toLowerCase();
    selectValue.innerText = this.innerText;
    filterFunc(selectedValue);

    lastClickedBtn.classList.remove("active");
    this.classList.add("active");
    lastClickedBtn = this;

  });

}



// contact form variables
const form = document.querySelector("[data-form]");
const formInputs = document.querySelectorAll("[data-form-input]");
const formBtn = document.querySelector("[data-form-btn]");

// add event to all form input field
for (let i = 0; i < formInputs.length; i++) {
  formInputs[i].addEventListener("input", function () {

    // check form validation
    if (form.checkValidity()) {
      formBtn.removeAttribute("disabled");
    } else {
      formBtn.setAttribute("disabled", "");
    }

  });
}



// page navigation variables
const navigationLinks = document.querySelectorAll("[data-nav-link]");
const pages = document.querySelectorAll("[data-page]");

// add event to all nav link
for (let i = 0; i < navigationLinks.length; i++) {
  navigationLinks[i].addEventListener("click", function () {

    for (let i = 0; i < pages.length; i++) {
      if (this.innerHTML.toLowerCase() === pages[i].dataset.page) {
        pages[i].classList.add("active");
        navigationLinks[i].classList.add("active");
        window.scrollTo(0, 0);
      } else {
        pages[i].classList.remove("active");
        navigationLinks[i].classList.remove("active");
      }
    }

  });
}

document.addEventListener('DOMContentLoaded', function() {
  // Attach click event to all publication-trigger links
  document.querySelectorAll('.publication-trigger').forEach(function(trigger) {
    trigger.addEventListener('click', function(event) {
      event.preventDefault(); // Prevent default link behavior
      // Toggle display of the associated project-summary element
      var summary = this.parentElement.querySelector('.project-summary');
      if (summary) {
        summary.style.display = (summary.style.display === 'block') ? 'none' : 'block';
      }
    });
  });
});
