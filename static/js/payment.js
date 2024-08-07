document.addEventListener("DOMContentLoaded", function () {
  const cardLinks = document.querySelectorAll(".cards a");
  const selectedCardInput = document.getElementById("selectedCard");

  cardLinks.forEach((cardLink) => {
    cardLink.addEventListener("click", function (e) {
      e.preventDefault();
      cardLinks.forEach((link) => link.classList.remove("selected"));
      this.classList.add("selected");
      selectedCardInput.value = this.dataset.card;
    });
  });
});
