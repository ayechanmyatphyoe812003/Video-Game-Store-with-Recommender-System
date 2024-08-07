const observer = new IntersectionObserver((entries) => {
  entries.forEach((entry) => {
    console.log(entry);
    if (entry.isIntersecting) {
      entry.target.classList.add("show");
    } else {
      entry.target.classList.remove("show");
    }
  });
});

const hiddenElements = document.querySelectorAll(".hidden");
hiddenElements.forEach((el) => observer.observe(el));

//checkbox
function changeColor(checkbox) {
  var checkboxButton = checkbox.parentNode;
  if (checkbox.checked) {
    checkboxButton.classList.add("checked");
  } else {
    checkboxButton.classList.remove("checked");
  }
}
