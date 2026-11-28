(() => {
  const chat = document.querySelector("#chat");
  const form = document.querySelector("#form");
  const input = document.querySelector("#question");
  document.querySelector(".notice").textContent = "Connected to the Agent API";
  document.querySelector(".scope").textContent = "SEC filing collection";
  document.querySelectorAll("[data-q]").forEach(button => button.remove());
  // Preserve the prototype's layout and chat history. Disable illustrative cards
  // in this build so example figures cannot be mistaken for API evidence.
  const liveMessage = message;
  message = (text, user = false) => liveMessage(text, user, false);
  document.querySelector("#dashboard").hidden = true;

  form.onsubmit = async (event) => {
    event.preventDefault();
    const query = input.value.trim();
    if (!query) return;
    const threadId = activeId;
    liveMessage(query, true);
    input.value = "";
    const pending = document.createElement("p");
    pending.setAttribute("role", "status");
    pending.textContent = "Searching SEC filings…";
    chat.append(pending);
    try {
      const response = await fetch("/query", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({query, top_k: 15, trace_id: crypto.randomUUID()})
      });
      if (!response.ok) throw new Error("Agent API request failed.");
      const result = await response.json();
      if (activeId !== threadId) return;
      const explanation = result.retrieval_limitation || (
        result.status === "NO_EVIDENCE" ? "Insufficient evidence in the SEC filings." :
        "Evidence found. Answer generation is currently disabled."
      );
      liveMessage(result.answer || result.error || explanation);
      const panel = document.createElement("div");
      panel.className = "sub";
      const detail = document.createElement("p");
      const usage = result.token_usage?.total_tokens;
      detail.textContent = [
        result.used_tool || result.selected_tool,
        result.trace_id && `Trace ${result.trace_id}`,
        Number.isFinite(result.latency_ms) && `${Math.round(result.latency_ms)} ms`,
        Number.isFinite(usage) && `${usage} tokens`
      ].filter(Boolean).join(" · ");
      panel.append(detail);
      const links = document.createElement("ul");
      const answerCitations = result.citations || [];
      const preview = !answerCitations.length && (result.retrieval_citations || []).length;
      if (preview) {
        const label = document.createElement("p");
        label.textContent = "Retrieved sources";
        panel.append(label);
      }
      for (const citation of preview ? result.retrieval_citations : answerCitations) {
        let url;
        try { url = new URL(citation.source_url); } catch { continue; }
        if (url.protocol !== "https:" || !["www.sec.gov", "sec.gov"].includes(url.host)
          || !url.pathname.startsWith("/Archives/edgar/data/")) continue;
        const link = document.createElement("a");
        link.href = url.href;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = [citation.ticker, citation.form, citation.reporting_period_end].filter(Boolean).join(" · ") || "SEC filing";
        const item = document.createElement("li");
        item.append(link);
        links.append(item);
      }
      if (links.childElementCount) panel.append(links);
      chat.append(panel);
    } catch {
      if (activeId === threadId) liveMessage("Could not reach the Agent API. Please try again.");
    } finally {
      pending.remove();
    }
  };
})();
