function clip() {
  var focus = getFocus();
  focus.addClass("keep");
}

function getFocus() {
  var ins = getLongest("ins");
  var del = getLongest("del");
  var focus = null;
  if (ins.text().length > del.text().length) {
    focus = ins;
  } else {
    focus = del;
  }
  return focus;
}

function getLongest(name) {
  var longest = $("<span></span>");
  $(name).each(function(i, e) {
    e = $(e);
    if ($(e).text().length > longest.text().length) {
      longest = e;
    }
  });
  return longest;
}
