(function () {
  "use strict";

  const builder = document.getElementById("rank-builder");
  if (!builder) return;

  const positionCount = parseInt(builder.dataset.positionCount, 10);
  const rankedList = document.getElementById("ranked-list");
  const poolList = document.getElementById("pool-list");
  const inputsContainer = document.getElementById("position-inputs");
  const announcer = document.getElementById("rank-announcer");
  const form = document.getElementById("predict-form");

  function announce(message) {
    if (announcer) announcer.textContent = message;
  }

  function driverName(card) {
    const el = card.querySelector(".driver-card-name");
    return el ? el.textContent : "driver";
  }

  function updateToggleButton(card, inRankedList) {
    const btn = card.querySelector(".toggle-btn");
    if (!btn) return;
    if (inRankedList) {
      btn.textContent = "−";
      btn.setAttribute("aria-label", "Remove " + driverName(card) + " from ranking");
    } else {
      btn.textContent = "+";
      btn.setAttribute("aria-label", "Add " + driverName(card) + " to ranking");
    }
  }

  function rebuildHiddenInputs() {
    inputsContainer.innerHTML = "";
    Array.from(rankedList.children).forEach((card, index) => {
      const input = document.createElement("input");
      input.type = "hidden";
      input.name = "position_" + (index + 1);
      input.value = card.dataset.driverId;
      inputsContainer.appendChild(input);
    });
  }

  function syncAll() {
    // Enforce ranked-list capacity: anything beyond positionCount falls back to the pool.
    while (poolList && rankedList.children.length > positionCount) {
      const excess = rankedList.lastElementChild;
      poolList.insertBefore(excess, poolList.firstChild);
    }

    Array.from(rankedList.children).forEach((card, index) => {
      card.querySelector(".position-badge").textContent = index + 1;
      updateToggleButton(card, true);
    });

    if (poolList) {
      Array.from(poolList.children).forEach((card) => {
        card.querySelector(".position-badge").textContent = "";
        updateToggleButton(card, false);
      });
    }

    rebuildHiddenInputs();
  }

  function moveCard(card, direction) {
    const sibling = direction === "up" ? card.previousElementSibling : card.nextElementSibling;
    if (!sibling) return;
    if (direction === "up") {
      card.parentElement.insertBefore(card, sibling);
    } else {
      card.parentElement.insertBefore(sibling, card);
    }
    card.focus();
    syncAll();
    const badge = card.querySelector(".position-badge").textContent;
    announce(driverName(card) + " moved to position " + badge);
  }

  function toggleCard(card) {
    const inRanked = card.parentElement === rankedList;
    if (inRanked) {
      poolList.insertBefore(card, poolList.firstChild);
      announce(driverName(card) + " removed from ranking");
    } else {
      rankedList.appendChild(card);
      announce(driverName(card) + " added to ranking");
    }
    card.focus();
    syncAll();
  }

  builder.addEventListener("click", (event) => {
    const btn = event.target.closest(".move-btn");
    if (!btn) return;
    const card = btn.closest(".driver-card");
    if (!card) return;
    if (btn.classList.contains("move-up")) moveCard(card, "up");
    else if (btn.classList.contains("move-down")) moveCard(card, "down");
    else if (btn.classList.contains("toggle-btn")) toggleCard(card);
  });

  if (window.Sortable) {
    const sortableOptions = {
      group: "ranking",
      handle: ".drag-handle",
      animation: 150,
      ghostClass: "driver-card-ghost",
      chosenClass: "driver-card-chosen",
      dragClass: "driver-card-drag",
      onEnd: syncAll,
    };
    Sortable.create(rankedList, sortableOptions);
    if (poolList) Sortable.create(poolList, sortableOptions);
  }

  if (form) {
    form.addEventListener("submit", (event) => {
      if (rankedList.children.length !== positionCount) {
        event.preventDefault();
        announce(
          "Please place all " + positionCount + " drivers in the predicted order before saving."
        );
      }
    });
  }

  syncAll();
})();
