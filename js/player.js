class Player {
  constructor(x, y) {
    this.x = x;
    this.y = y;
    this.width = 40;
    this.height = 40;
    this.vx = 0;      // Velocidad horizontal
    this.vy = 0;      // Velocidad vertical
    this.jumping = false;
    // La imagen se asignará de forma centralizada desde game.js
  }
  move(dx) {
    this.x += dx;
  }
  jump() {
    this.vy = -7; // Ajusta el salto para una sensación natural
    this.jumping = true;
  }
  draw(ctx) {
    if (this.image) {
      ctx.drawImage(this.image, this.x, this.y, this.width, this.height);
    } else {
      ctx.fillStyle = "orange";
      ctx.fillRect(this.x, this.y, this.width, this.height);
      ctx.fillStyle = "black";
      ctx.fillRect(this.x + 10, this.y + 10, 5, 5);
      ctx.fillRect(this.x + 25, this.y + 10, 5, 5);
    }
  }
}
