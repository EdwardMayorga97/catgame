class Finish {
  constructor(x, y) {
    this.x = x;
    this.y = y;
    this.size = 20;
    // La imagen se asignará de forma centralizada desde game.js
  }
  draw(ctx) {
    if (this.image) {
      ctx.drawImage(this.image, this.x, this.y, this.size, this.size);
    } else {
      ctx.fillStyle = "pink";
      ctx.fillRect(this.x, this.y, this.size, this.size);
      // Dibujar orejas sencillas (opcional)
      ctx.fillStyle = "black";
      ctx.fillRect(this.x - 4, this.y, 4, 4);
      ctx.fillRect(this.x + this.size, this.y, 4, 4);
    }
  }
}
