document.addEventListener("DOMContentLoaded", function (){
  const params = new URLSearchParams(window.location.search);
  const ext = params.get("ext");
  const agency = params.get("agency") || "";
  const id = params.get("id");
  const lookup = ext || id;
  if(!lookup) return;

  const selector =
    "[data-external-id='"+lookup+"'], "+
    "[data-id='"+lookup+"'], "+
    "[data-opportunity='"+lookup+"']";

  const row = document.querySelector(selector);
  if(row){
    row.scrollIntoView({behavior:"smooth",block:"center"});
    row.classList.add("highlight-opportunity");
    setTimeout(()=> row.classList.remove("highlight-opportunity"), 1600);
  }
  if(typeof openDetailModal === "function"){ openDetailModal(lookup, agency); }
});
