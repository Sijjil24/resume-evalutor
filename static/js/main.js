// Theme
const root = document.documentElement;
const navToggle = document.getElementById("nav-menu-toggle");
const mainNav = document.getElementById("main-nav");
if (navToggle && mainNav) {
  navToggle.addEventListener("click", () => {
    const isOpen = mainNav.classList.toggle("open");
    navToggle.setAttribute("aria-expanded", String(isOpen));
    navToggle.setAttribute("aria-label", isOpen ? "Close navigation" : "Open navigation");
  });
}

// Mobile dropdown menus: tap to expand
document.querySelectorAll(".nav-dropdown-toggle").forEach((toggle) => {
  toggle.addEventListener("click", (event) => {
    if (window.innerWidth > 760) return; // handled by CSS hover on desktop
    event.stopPropagation();
    const dropdown = toggle.closest(".nav-dropdown");
    dropdown.classList.toggle("open");
  });
});


const themeToggle = document.getElementById("theme-toggle");
if (themeToggle) {
  const paintThemeIcon = () => {
    const dark = root.dataset.theme === "dark";
    themeToggle.setAttribute("aria-checked", String(dark));
    themeToggle.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
    themeToggle.title = dark ? "Switch to light mode" : "Switch to dark mode";
    themeToggle.querySelector(".theme-icon-light").hidden = dark;
    themeToggle.querySelector(".theme-icon-dark").hidden = !dark;
  };
  paintThemeIcon();
  themeToggle.addEventListener("click", () => {
    const next = root.dataset.theme === "dark" ? "light" : "dark";
    root.dataset.theme = next;
    localStorage.setItem("theme", next);
    paintThemeIcon();
  });
}

// Template filters
document.querySelectorAll("[data-filter]").forEach((button) => {
  button.addEventListener("click", () => {
    const filter = button.dataset.filter;
    document.querySelectorAll("[data-filter]").forEach((item) => item.classList.toggle("active", item === button));
    document.querySelectorAll(".gallery-card").forEach((card) => {
      card.hidden = filter !== "All" && card.dataset.category !== filter;
    });
  });
});

document.querySelectorAll("[data-carousel]").forEach((button) => {
  button.addEventListener("click", () => {
    const carousel = document.getElementById(button.dataset.carousel);
    if (carousel) carousel.scrollBy({ left: Number(button.dataset.direction) * carousel.clientWidth * .72, behavior: "smooth" });
  });
});

// Resume upload and review
const analyzeForm = document.getElementById("analyze-form");
if (analyzeForm) {
  const fileInput = document.getElementById("file");
  const drop = document.getElementById("drop");
  const dropText = document.getElementById("drop-text");
  const button = document.getElementById("btn");
  const errorBox = document.getElementById("error");
  if (fileInput && drop && dropText && button && errorBox) {
    fileInput.addEventListener("change", () => {
      if (fileInput.files[0]) dropText.textContent = fileInput.files[0].name;
    });
    ["dragover", "dragenter"].forEach((eventName) => drop.addEventListener(eventName, (event) => {
      event.preventDefault();
      drop.classList.add("over");
    }));
    ["dragleave", "drop"].forEach((eventName) => drop.addEventListener(eventName, () => drop.classList.remove("over")));
    drop.addEventListener("drop", (event) => {
      event.preventDefault();
      if (event.dataTransfer.files.length) {
        fileInput.files = event.dataTransfer.files;
        dropText.textContent = fileInput.files[0].name;
      }
    });
    analyzeForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      errorBox.textContent = "";
      if (!fileInput.files[0]) {
        errorBox.textContent = "Please choose a file.";
        return;
      }
      button.disabled = true;
      button.textContent = "Reviewing your resume…";
      analyzeForm.classList.add("is-loading");
      try {
        const response = await fetch("/analyze", { method: "POST", body: new FormData(analyzeForm) });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "The review could not be completed.");
        window.location.href = data.redirect;
      } catch (error) {
        errorBox.textContent = error.message.includes("JSON")
          ? "Your session expired. Refresh the page and sign in again."
          : error.message;
        button.disabled = false;
        button.textContent = "Get my review";
        analyzeForm.classList.remove("is-loading");
      }
    });
  }
}

// Guided resume builder
const builder = document.getElementById("resume-builder");
if (builder) {
  const steps = [...builder.querySelectorAll(".editor-step")];
  const stepButtons = [...builder.querySelectorAll("[data-step-button]")];
  const paper = document.getElementById("resume-paper");
  const saveState = document.getElementById("save-state");
  const saveButton = document.getElementById("save-resume");
  const titleInput = document.getElementById("resume-title");
  const toast = document.getElementById("builder-toast");
  let activeStep = 0;
  let saveTimer;
  let toastTimer;

  const showToast = (message, isError = false) => {
    toast.textContent = message;
    toast.classList.toggle("error", isError);
    toast.classList.add("visible");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => toast.classList.remove("visible"), 3200);
  };

  const getData = () => {
    const data = {};
    builder.querySelectorAll("[data-field]").forEach((field) => {
      data[field.dataset.field] = field.value.trim();
    });
    ["experience", "education", "projects", "custom_sections"].forEach((group) => {
      data[group] = [...builder.querySelectorAll(`[data-group="${group}"]`)].map((card) => {
        const item = {};
        card.querySelectorAll("[data-key]").forEach((field) => { item[field.dataset.key] = field.value.trim(); });
        return item;
      });
    });
    data.template = builder.querySelector('[data-setting="template"]').value;
    data.accent = paper.style.getPropertyValue("--resume-accent").trim() || "#0F766E";
    data.font = builder.querySelector('[data-setting="font"]').value;
    data.font_size = Number(builder.querySelector('[data-setting="font_size"]').value);
    data.spacing = builder.querySelector('[data-setting="spacing"]').value;
    data.section_order = [...builder.querySelectorAll(".order-item")].map((item) => item.dataset.order);
    data.photo = document.getElementById("preview-photo").getAttribute("src") || "";
    return data;
  };

  const updateText = (key, text) => {
    const node = paper.querySelector(`[data-preview="${key}"]`);
    if (node) node.textContent = text;
  };

  const escapeText = (text) => {
    const node = document.createElement("span");
    node.textContent = text;
    return node.innerHTML;
  };

  const refreshPreview = () => {
    const data = getData();
    ["name", "title", "email", "phone", "location", "links", "summary", "skills"].forEach((key) => {
      updateText(key, data[key] || (key === "name" ? "Your Name" : key === "title" ? "Professional title" : ""));
    });
    paper.querySelector('[data-preview-section="summary"]').hidden = !data.summary;
    paper.querySelector('[data-preview-section="skills"]').hidden = !data.skills;
    document.getElementById("preview-experience").innerHTML = data.experience.filter((item) => item.role || item.company).map((item) =>
      `<div class="preview-entry"><div><b>${escapeText(item.role || "")}</b><span>${escapeText(item.start || "")}${item.end ? ` — ${escapeText(item.end)}` : ""}</span></div><small>${escapeText(item.company || "")}${item.location ? ` · ${escapeText(item.location)}` : ""}</small><p>${escapeText(item.bullets || "")}</p></div>`
    ).join("");
    document.getElementById("preview-education").innerHTML = data.education.filter((item) => item.degree || item.school).map((item) =>
      `<div class="preview-entry"><div><b>${escapeText(item.degree || "")}</b><span>${escapeText(item.start || "")}${item.end ? ` — ${escapeText(item.end)}` : ""}</span></div><small>${escapeText(item.school || "")}</small></div>`
    ).join("");
    document.getElementById("preview-projects").innerHTML = data.projects.filter((item) => item.name || item.description).map((item) =>
      `<div class="preview-entry"><div><b>${escapeText(item.name || "")}</b></div>${item.link ? `<small>${escapeText(item.link)}</small>` : ""}<p>${escapeText(item.description || "")}</p></div>`
    ).join("");
    paper.querySelector('[data-preview-section="projects"]').hidden = !data.projects.some((item) => item.name || item.description);
    document.getElementById("preview-custom").innerHTML = data.custom_sections.filter((item) => item.title || item.content).map((item) =>
      `<section><h3>${escapeText(item.title || "Additional information")}</h3><p>${escapeText(item.content || "")}</p></section>`
    ).join("");
    paper.className = `resume-document template-${data.template} spacing-${data.spacing}`;
    paper.style.setProperty("--resume-accent", data.accent);
    paper.style.setProperty("--resume-font-size", `${data.font_size}pt`);
    paper.style.fontFamily = data.font === "Merriweather" ? "Merriweather, Georgia, serif" : data.font === "Source Sans" ? '"Source Sans 3", Arial, sans-serif' : "Lato, Arial, sans-serif";
    const previewSections = paper.querySelector(".paper-preview-sections");
    data.section_order.forEach((name) => {
      const section = previewSections.querySelector(`[data-preview-section="${name}"]`);
      if (section) previewSections.appendChild(section);
    });
    updatePageCount();
  };

  const updatePageCount = () => {
    const words = [...builder.querySelectorAll("[data-field], [data-key]")].reduce((sum, field) => sum + field.value.trim().split(/\s+/).filter(Boolean).length, 0);
    const count = Math.max(1, Math.ceil(words / 430));
    document.getElementById("page-counter").textContent = `About ${count} ${count === 1 ? "page" : "pages"}`;
    document.getElementById("page-warning").textContent = count > 2 ? "This draft may run longer than two pages. Consider shortening less relevant details." : "";
  };

  const setStep = (index) => {
    activeStep = Math.max(0, Math.min(steps.length - 1, index));
    steps.forEach((step, stepIndex) => {
      step.hidden = stepIndex !== activeStep;
      step.classList.toggle("active", stepIndex === activeStep);
    });
    stepButtons.forEach((button, stepIndex) => {
      button.classList.toggle("active", stepIndex === activeStep);
      button.classList.toggle("complete", stepIndex < activeStep);
      if (stepIndex === activeStep) button.setAttribute("aria-current", "step");
      else button.removeAttribute("aria-current");
    });
    document.getElementById("progress-fill").style.width = `${(activeStep / (steps.length - 1)) * 100}%`;
    document.getElementById("step-back").disabled = activeStep === 0;
    const next = document.getElementById("step-next");
    next.textContent = activeStep === steps.length - 1 ? "Finish" : "Next step →";
    document.getElementById("step-count").textContent = `Step ${activeStep + 1} of ${steps.length}`;
  };

  const saveResume = async (quiet = false) => {
    saveState.textContent = "Saving…";
    try {
      const response = await fetch(builder.dataset.saveUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: titleInput.value, data: getData() }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Could not save your resume.");
      saveState.textContent = "All changes saved";
      if (!quiet) showToast("Your resume is saved.");
      return true;
    } catch (error) {
      saveState.textContent = "Save failed";
      if (!quiet) showToast(error.message, true);
      return false;
    }
  };

  const queueSave = () => {
    saveState.textContent = "Unsaved changes";
    window.clearTimeout(saveTimer);
    saveTimer = window.setTimeout(() => saveResume(true), 900);
  };

  const addGroup = (group) => {
    const card = document.createElement("fieldset");
    card.className = group === "custom_sections" ? "repeat-card custom-section" : "repeat-card";
    card.dataset.group = group;
    if (group === "experience") {
      card.innerHTML = '<legend>Experience</legend><button class="remove-entry" type="button">Remove</button><div class="form-grid"><div><label>Job title</label><input data-key="role" type="text"></div><div><label>Company</label><input data-key="company" type="text"></div><div><label>Location</label><input data-key="location" type="text"></div><div><label>Dates</label><div class="form-grid"><input data-key="start" type="text" aria-label="Start date"><input data-key="end" type="text" aria-label="End date"></div></div><div class="field-wide"><label>What did you accomplish?</label><textarea data-key="bullets" rows="4"></textarea><button class="helper-button" type="button" data-helper="bullet">Improve this bullet</button></div></div>';
      document.getElementById("experience-list").appendChild(card);
    } else if (group === "education") {
      card.innerHTML = '<legend>Education</legend><button class="remove-entry" type="button">Remove</button><div class="form-grid"><div class="field-wide"><label>Degree or qualification</label><input data-key="degree" type="text"></div><div class="field-wide"><label>School</label><input data-key="school" type="text"></div><div><label>Start</label><input data-key="start" type="text"></div><div><label>End</label><input data-key="end" type="text"></div></div>';
      document.getElementById("education-list").appendChild(card);
    } else if (group === "projects") {
      card.innerHTML = '<legend>Project</legend><button class="remove-entry" type="button">Remove</button><label>Project name</label><input data-key="name" type="text"><label>Link (optional)</label><input data-key="link" type="text"><label>What did you do?</label><textarea data-key="description" rows="3"></textarea>';
      document.getElementById("projects-list").appendChild(card);
    } else {
      card.innerHTML = '<legend>Custom section</legend><button class="remove-entry" type="button">Remove</button><label>Section title</label><input data-key="title" type="text" placeholder="Certifications, Languages, Volunteering"><label>Details</label><textarea data-key="content" rows="3"></textarea>';
      document.getElementById("custom-section-list").appendChild(card);
    }
    card.querySelector("input, textarea")?.focus();
    refreshPreview();
    queueSave();
  };

  builder.addEventListener("input", (event) => {
    if (event.target.matches("[data-field], [data-key], #resume-title, [data-setting]")) {
      refreshPreview();
      queueSave();
    }
  });
  builder.addEventListener("change", (event) => {
    if (event.target.matches("[data-setting]")) {
      refreshPreview();
      queueSave();
    }
  });
  builder.querySelectorAll("[data-step-button]").forEach((button) => button.addEventListener("click", () => setStep(Number(button.dataset.stepButton))));
  document.getElementById("step-back").addEventListener("click", () => setStep(activeStep - 1));
  document.getElementById("step-next").addEventListener("click", async () => {
    if (activeStep === steps.length - 1) {
      if (await saveResume()) showToast("Your resume is ready to print or save as PDF.");
    } else {
      setStep(activeStep + 1);
    }
  });
  saveButton.addEventListener("click", () => saveResume());
  builder.querySelectorAll("[data-add]").forEach((button) => button.addEventListener("click", () => addGroup(button.dataset.add)));
  builder.addEventListener("click", async (event) => {
    const remove = event.target.closest(".remove-entry");
    if (remove) {
      const cards = [...builder.querySelectorAll(`[data-group="${remove.closest("[data-group]").dataset.group}"]`)];
      if (cards.length === 1) {
        cards[0].querySelectorAll("[data-key]").forEach((field) => { field.value = ""; });
      } else {
        remove.closest("[data-group]").remove();
      }
      refreshPreview();
      queueSave();
      return;
    }
    const move = event.target.closest("[data-move]");
    if (move) {
      const item = move.closest(".order-item");
      const siblings = [...item.parentElement.children];
      const index = siblings.indexOf(item);
      const destination = index + Number(move.dataset.move);
      if (destination >= 0 && destination < siblings.length) {
        if (destination < index) item.parentElement.insertBefore(item, siblings[destination]);
        else siblings[destination].after(item);
        refreshPreview();
        queueSave();
      }
      return;
    }
    const helper = event.target.closest("[data-helper]");
    if (helper) {
      const action = helper.dataset.helper;
      const experienceCard = helper.closest("[data-group='experience']");
      const bulletInput = experienceCard?.querySelector('[data-key="bullets"]');
      const content = action === "bullet" ? (bulletInput?.value || "") :
        action === "summary" ? getData().experience.map((item) => `${item.role} ${item.company} ${item.bullets}`).join("\n").trim() :
        document.getElementById("target-role").value;
      const role = document.getElementById("target-role").value || document.getElementById("title").value;
      helper.disabled = true;
      helper.textContent = "Working…";
      try {
        const response = await fetch(builder.dataset.helperUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action, content, role }),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "The writing helper could not complete.");
        if (action === "summary") document.getElementById("summary").value = result.text;
        else if (action === "bullet" && bulletInput) bulletInput.value = result.text;
        else if (action === "skills") {
          const input = document.getElementById("skills");
          input.value = [input.value.trim(), result.text].filter(Boolean).join(", ");
        }
        refreshPreview();
        queueSave();
        showToast("Suggestion added. Review it before using.");
      } catch (error) {
        showToast(error.message, true);
      } finally {
        helper.disabled = false;
        helper.textContent = action === "bullet" ? "Improve this bullet" : action === "summary" ? "Write my summary" : "Suggest skills for this job title";
      }
    }
  });
  builder.querySelectorAll("[data-accent]").forEach((button) => button.addEventListener("click", () => {
    paper.style.setProperty("--resume-accent", button.dataset.accent);
    builder.querySelectorAll("[data-accent]").forEach((swatch) => swatch.classList.toggle("selected", swatch === button));
    queueSave();
  }));
  document.getElementById("photo-input").addEventListener("change", (event) => {
    const file = event.target.files[0];
    if (!file) return;
    if (file.size > 100 * 1024) {
      showToast("Choose an image under 100 KB.", true);
      event.target.value = "";
      return;
    }
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
      showToast("Choose a JPG, PNG, or WebP image.", true);
      event.target.value = "";
      return;
    }
    const reader = new FileReader();
    reader.addEventListener("load", () => {
      document.getElementById("preview-photo").src = reader.result;
      document.getElementById("preview-photo").hidden = false;
      queueSave();
    });
    reader.readAsDataURL(file);
  });
  refreshPreview();
  setStep(0);
  saveState.textContent = "All changes saved";
}
