async function load() {
  const res = await fetch("./jobs.json", { cache: "no-store" });
  if (!res.ok) throw new Error("jobs.json missing — run the daily matcher first");
  return res.json();
}

function fmtWhen(iso) {
  if (!iso) return "unknown";
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

function render(data) {
  const list = document.getElementById("list");
  const meta = document.getElementById("meta");
  const banner = document.getElementById("banner");
  const q = document.getElementById("q").value.trim().toLowerCase();
  const resume = document.getElementById("resume").value;
  const sort = document.getElementById("sort").value;

  let jobs = [...(data.jobs || [])];
  if (resume) jobs = jobs.filter((j) => j.resume_id === resume);
  if (q) {
    jobs = jobs.filter((j) =>
      `${j.title} ${j.company} ${j.matched_skills} ${j.matched_role} ${j.location}`
        .toLowerCase()
        .includes(q)
    );
  }
  if (sort === "fresh") {
    jobs.sort((a, b) => String(b.posted_at).localeCompare(String(a.posted_at)));
  } else {
    jobs.sort((a, b) => (b.match_score || 0) - (a.match_score || 0));
  }

  meta.innerHTML = `
    <span><strong>${data.count ?? jobs.length}</strong> matches</span>
    <span>Updated <strong>${fmtWhen(data.generated_at)}</strong></span>
    <span>Showing <strong>${jobs.length}</strong></span>
  `;

  if (data.meta?.needs_api_keys) {
    banner.hidden = false;
    banner.textContent =
      data.meta.message ||
      "Add RAPIDAPI_KEY (JSearch) and/or JOOBLE_API_KEY in GitHub Secrets for Dubai/Abu Dhabi jobs. Worldwide remote fillers are turned off.";
  } else {
    banner.hidden = true;
  }

  if (!jobs.length) {
    list.innerHTML = `<div class="empty">
      No React Native / Full Stack matches in Dubai–Abu Dhabi on tracked company career pages right now.
      The daily job keeps checking Careem, Deliveroo, GitLab, and other boards in <code>boards.yaml</code>.
      For wider UAE coverage (Indeed etc. via Google for Jobs), subscribe to JSearch Basic ($0) and add <code>RAPIDAPI_KEY</code>.
    </div>`;
    return;
  }

  list.innerHTML = jobs
    .map((j, i) => {
      const resumeClass = j.resume_id === "6+" ? "resume-6" : "resume-5";
      return `
      <article class="job" style="animation-delay:${Math.min(i, 12) * 40}ms">
        <div class="score">${Math.round(j.match_score ?? 0)}</div>
        <div>
          <h2>${escapeHtml(j.title || "")}</h2>
          <div class="company">${escapeHtml(j.company || "")} · ${escapeHtml(j.location || "")}</div>
          <div class="tags">
            <span class="tag ${resumeClass}">Resume ${escapeHtml(j.resume_id || "")}</span>
            <span class="tag">${escapeHtml(j.matched_role || "role n/a")}</span>
            <span class="tag">${escapeHtml(j.source || "")}</span>
            <span class="tag">${j.age_hours != null ? `~${j.age_hours}h` : "age n/a"}</span>
          </div>
          <p class="why">${escapeHtml(j.why_match || "")}</p>
        </div>
        <div class="actions">
          <a href="${escapeAttr(j.url || "#")}" target="_blank" rel="noopener">Open job</a>
          <a class="secondary" href="mailto:athul290@gmail.com?subject=${encodeURIComponent("Apply help: " + (j.title || ""))}&body=${encodeURIComponent("Please draft apply materials for:\\n" + (j.url || ""))}">Request draft</a>
        </div>
      </article>`;
    })
    .join("");
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function escapeAttr(s) {
  return escapeHtml(s).replaceAll("'", "&#39;");
}

async function boot() {
  try {
    const data = await load();
    const redraw = () => render(data);
    ["q", "resume", "sort"].forEach((id) =>
      document.getElementById(id).addEventListener("input", redraw)
    );
    redraw();
  } catch (err) {
    document.getElementById("meta").textContent = String(err.message || err);
    document.getElementById("list").innerHTML =
      `<div class="empty">Run <code>python src/run_daily.py</code> to generate jobs.json</div>`;
  }
}

boot();
