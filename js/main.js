/* ==========================================================
   Framewerk Studio – Interaktionen
   ========================================================== */

document.documentElement.classList.remove("no-js");

const header = document.querySelector(".site-header");
const navToggle = document.querySelector(".nav-toggle");
const navMenu = document.querySelector(".nav-menu");

/* ---------- Header beim Scrollen abdunkeln ---------- */
function updateHeader() {
  header.classList.toggle("scrolled", window.scrollY > 20);
}
updateHeader();
window.addEventListener("scroll", updateHeader, { passive: true });

/* ---------- Mobiles Menü ---------- */
function setMenu(open) {
  navToggle.setAttribute("aria-expanded", String(open));
  navToggle.setAttribute("aria-label", open ? "Menü schließen" : "Menü öffnen");
  navMenu.classList.toggle("open", open);
  document.body.classList.toggle("no-scroll", open);
}

navToggle.addEventListener("click", () => {
  setMenu(navToggle.getAttribute("aria-expanded") !== "true");
});

navMenu.querySelectorAll("a").forEach((link) => {
  link.addEventListener("click", () => setMenu(false));
});

/* ---------- Aktiven Menüpunkt markieren ---------- */
const navLinks = [...navMenu.querySelectorAll('a[href^="#"]')];
const sections = navLinks
  .map((link) => document.querySelector(link.getAttribute("href")))
  .filter(Boolean);

const sectionObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      navLinks.forEach((link) => {
        link.classList.toggle("active", link.getAttribute("href") === "#" + entry.target.id);
      });
    });
  },
  { rootMargin: "-45% 0px -50% 0px" }
);
sections.forEach((section) => sectionObserver.observe(section));

/* ---------- Sanfte Scroll-Animationen ---------- */
const revealEls = document.querySelectorAll(".reveal");

// Elemente im selben Raster leicht zeitversetzt einblenden
document.querySelectorAll(".cards, .work-grid, .steps, .quotes, .hero-content").forEach((group) => {
  group.querySelectorAll(":scope > .reveal").forEach((el, i) => {
    el.style.setProperty("--delay", `${i * 0.1}s`);
  });
});

const revealObserver = new IntersectionObserver(
  (entries, observer) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add("is-visible");
      observer.unobserve(entry.target);
    });
  },
  { threshold: 0.15, rootMargin: "0px 0px -40px 0px" }
);
revealEls.forEach((el) => revealObserver.observe(el));

/* ---------- Hero-Video: Platzhalter, falls keine Datei vorhanden ---------- */
const heroVideo = document.querySelector(".hero-video");
if (heroVideo) {
  const source = heroVideo.querySelector("source");
  const hideVideo = () => heroVideo.classList.add("is-missing");
  if (source) source.addEventListener("error", hideVideo);
  heroVideo.addEventListener("error", hideVideo);
}

/* ---------- Video-Popup ---------- */
const modal = document.getElementById("video-modal");
const modalBody = document.getElementById("modal-body");
const modalTitle = document.getElementById("modal-title");
let lastFocused = null;

function embedUrl(url) {
  const yt = url.match(/(?:youtube\.com\/(?:watch\?v=|shorts\/|embed\/)|youtu\.be\/)([\w-]{11})/);
  if (yt) return `https://www.youtube-nocookie.com/embed/${yt[1]}?autoplay=1&rel=0`;
  const vimeo = url.match(/vimeo\.com\/(\d+)/);
  if (vimeo) return `https://player.vimeo.com/video/${vimeo[1]}?autoplay=1`;
  return null;
}

function renderPlaceholder() {
  modalBody.innerHTML = `
    <div class="modal-placeholder">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>
      <strong>Video-Platzhalter</strong>
      <span>Hier erscheint später das Projektvideo.</span>
    </div>`;
}

function openModal(src, title) {
  lastFocused = document.activeElement;
  modalTitle.textContent = title || "";
  modalBody.innerHTML = "";

  const embed = src ? embedUrl(src) : null;

  if (embed) {
    const iframe = document.createElement("iframe");
    iframe.src = embed;
    iframe.title = title || "Video";
    iframe.allow = "autoplay; fullscreen; picture-in-picture";
    iframe.allowFullscreen = true;
    modalBody.appendChild(iframe);
  } else if (src) {
    const video = document.createElement("video");
    video.src = src;
    video.controls = true;
    video.autoplay = true;
    video.playsInline = true;
    video.addEventListener("error", renderPlaceholder);
    modalBody.appendChild(video);
  } else {
    renderPlaceholder();
  }

  modal.hidden = false;
  document.body.classList.add("no-scroll");
  requestAnimationFrame(() => modal.classList.add("open"));
  modal.querySelector(".modal-close").focus();
}

function closeModal() {
  modal.classList.remove("open");
  document.body.classList.remove("no-scroll");
  setTimeout(() => {
    modal.hidden = true;
    modalBody.innerHTML = ""; // stoppt das Video
  }, 300);
  if (lastFocused) lastFocused.focus();
}

document.querySelectorAll(".work").forEach((item) => {
  item.addEventListener("click", () => openModal(item.dataset.video, item.dataset.title));
});

modal.querySelectorAll("[data-close]").forEach((el) => el.addEventListener("click", closeModal));

document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  if (!modal.hidden) closeModal();
  else if (navMenu.classList.contains("open")) setMenu(false);
});

/* ---------- Kontaktformular ---------- */
const form = document.getElementById("contact-form");

if (form) {
  const status = form.querySelector(".form-status");
  const messages = {
    name: "Bitte gib deinen Namen ein.",
    email: "Bitte gib eine gültige E-Mail-Adresse ein.",
    type: "Bitte wähle die Art des Projekts.",
    message: "Bitte schreib uns kurz, worum es geht.",
  };

  function validateField(input) {
    const field = input.closest(".field");
    const error = field.querySelector(".error");
    const valid = input.checkValidity() && input.value.trim() !== "";
    field.classList.toggle("has-error", !valid);
    error.textContent = valid ? "" : messages[input.name];
    return valid;
  }

  form.querySelectorAll(".field input, .field select, .field textarea").forEach((input) => {
    input.addEventListener("blur", () => validateField(input));
    input.addEventListener("input", () => {
      if (input.closest(".field").classList.contains("has-error")) validateField(input);
    });
  });

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    status.textContent = "";
    status.className = "form-status";

    const inputs = [...form.querySelectorAll(".field input, .field select, .field textarea")];
    const fieldsValid = inputs.map(validateField).every(Boolean);

    const consent = form.querySelector('[name="consent"]');
    const consentError = form.querySelector(".consent-error");
    consentError.textContent = consent.checked ? "" : "Bitte stimme der Datenschutzerklärung zu.";

    if (!fieldsValid || !consent.checked) {
      const firstInvalid = form.querySelector(".has-error input, .has-error select, .has-error textarea") || consent;
      firstInvalid.focus();
      return;
    }

    /*
      Demo: Es wird nichts verschickt.
      Für echten Versand z. B. einen Dienst wie Formspree nutzen
      und hier per fetch() an dessen Adresse senden (siehe README).
    */
    status.textContent = "Danke! Deine Anfrage ist angekommen – wir melden uns bald. (Demo: Es wurde nichts versendet.)";
    status.classList.add("success");
    form.reset();
  });
}

/* ---------- Jahr im Footer ---------- */
const year = document.getElementById("year");
if (year) year.textContent = new Date().getFullYear();
