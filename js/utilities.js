// Determina si dos rectángulos se solapan.
function isOverlapping(rect1, rect2) {
  return (
    rect1.x < rect2.x + rect2.width &&
    rect1.x + rect1.width > rect2.x &&
    rect1.y < rect2.y + rect2.height &&
    rect1.y + rect1.height > rect2.y
  );
}

// Comprueba si el rectángulo 'rect' se solapa con algún objeto de un arreglo 'arr'.
// Los objetos pueden tener propiedades "width"/"height" o "size" (para objetos circulares).
function overlapsAny(rect, arr) {
  for (let obj of arr) {
    let objRect = {
      x: obj.x,
      y: obj.y,
      width: obj.size || obj.width,
      height: obj.size || obj.height
    };
    if (isOverlapping(rect, objRect)) {
      return true;
    }
  }
  return false;
}
