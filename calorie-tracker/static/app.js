(function () {
  const entryDate = window.ENTRY_DATE;

  // --- tab switching ---
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach((c) => c.classList.add("hidden"));
      btn.classList.add("active");
      document.getElementById("tab-" + btn.dataset.tab).classList.remove("hidden");
    });
  });

  function renderReview(container, estimate, extra) {
    container.classList.remove("hidden");
    container.innerHTML = `
      <div class="review-item">${escapeHtml(estimate.item || "Estimated meal")}
        <span style="font-weight:400;color:var(--muted);font-size:12px;">(${estimate.confidence || "?"} confidence)</span>
      </div>
      ${estimate.notes ? `<div class="review-notes">${escapeHtml(estimate.notes)}</div>` : ""}
      <div class="review-fields">
        <label>Calories<input type="number" class="f-calories" value="${estimate.calories ?? 0}"></label>
        <label>Protein g<input type="number" step="0.1" class="f-protein" value="${estimate.protein_g ?? ""}"></label>
        <label>Carbs g<input type="number" step="0.1" class="f-carbs" value="${estimate.carbs_g ?? ""}"></label>
        <label>Fat g<input type="number" step="0.1" class="f-fat" value="${estimate.fat_g ?? ""}"></label>
      </div>
      <button type="button" class="save-estimate-btn">Save to log</button>
    `;

    container.querySelector(".save-estimate-btn").addEventListener("click", () => {
      const form = document.createElement("form");
      form.method = "post";
      form.action = "/add";

      const fields = {
        entry_date: entryDate,
        source: extra.source,
        description: estimate.item || "",
        calories: container.querySelector(".f-calories").value || 0,
        protein_g: container.querySelector(".f-protein").value,
        carbs_g: container.querySelector(".f-carbs").value,
        fat_g: container.querySelector(".f-fat").value,
      };
      if (extra.photo_path) fields.photo_path = extra.photo_path;

      Object.entries(fields).forEach(([name, value]) => {
        const input = document.createElement("input");
        input.type = "hidden";
        input.name = name;
        input.value = value;
        form.appendChild(input);
      });
      document.body.appendChild(form);
      form.submit();
    });
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function showError(el, message) {
    el.textContent = message;
    el.classList.remove("hidden");
  }

  // --- describe meal (text) ---
  const describeBtn = document.getElementById("describe-analyze-btn");
  if (describeBtn) {
    describeBtn.addEventListener("click", async () => {
      const textEl = document.getElementById("describe-text");
      const errorEl = document.getElementById("describe-error");
      const reviewEl = document.getElementById("describe-review");
      errorEl.classList.add("hidden");
      reviewEl.classList.add("hidden");

      const description = textEl.value.trim();
      if (!description) {
        showError(errorEl, "Describe the meal first.");
        return;
      }

      describeBtn.disabled = true;
      describeBtn.textContent = "Analyzing...";
      try {
        const res = await fetch("/api/analyze/text", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ description }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Analysis failed.");
        renderReview(reviewEl, data, { source: "ai_text" });
      } catch (err) {
        showError(errorEl, err.message);
      } finally {
        describeBtn.disabled = false;
        describeBtn.textContent = "Analyze with AI";
      }
    });
  }

  // --- photo ---
  const photoFile = document.getElementById("photo-file");
  const photoPreview = document.getElementById("photo-preview");
  if (photoFile) {
    photoFile.addEventListener("change", () => {
      photoPreview.innerHTML = "";
      const file = photoFile.files[0];
      if (!file) return;
      const img = document.createElement("img");
      img.src = URL.createObjectURL(file);
      photoPreview.appendChild(img);
    });
  }

  const photoBtn = document.getElementById("photo-analyze-btn");
  if (photoBtn) {
    photoBtn.addEventListener("click", async () => {
      const errorEl = document.getElementById("photo-error");
      const reviewEl = document.getElementById("photo-review");
      errorEl.classList.add("hidden");
      reviewEl.classList.add("hidden");

      const file = photoFile.files[0];
      if (!file) {
        showError(errorEl, "Choose a photo first.");
        return;
      }

      const formData = new FormData();
      formData.append("photo", file);
      formData.append("description", document.getElementById("photo-caption").value.trim());

      photoBtn.disabled = true;
      photoBtn.textContent = "Analyzing...";
      try {
        const res = await fetch("/api/analyze/photo", {
          method: "POST",
          body: formData,
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Analysis failed.");
        renderReview(reviewEl, data, { source: "ai_photo", photo_path: data.photo_path });
      } catch (err) {
        showError(errorEl, err.message);
      } finally {
        photoBtn.disabled = false;
        photoBtn.textContent = "Analyze with AI";
      }
    });
  }
})();
