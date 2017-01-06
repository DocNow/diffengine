function clip() {
  var p = getParagraph();
  console.log(p);
  p.css({border: "thin solid black"});
  $('.diff').children().hide();
  $(p).show();
  $(p).parent().show();
}

function getParagraph() {
  var p = null;
  var largest = 0;
  $("p").each(function(i, e) {
    var len = changesLength(e);
    if (len > largest) {
      p = e;
      largest = len;
    }
  });
  return $(p);
}

function changesLength(p) {
  return count(p, 'del') + count(p, 'ins');
}

function count(e, sel) {
  var length = 0;
  $(e).children(sel).each(function(i, c) {
    console.log($(c).text());
    length += $(c).text().length; 
  });
  return length;
}
