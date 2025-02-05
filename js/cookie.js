class Cookie {
  constructor(x, y) {
    this.x = x;
    this.y = y;
    this.size = 15;
    // La imagen se asignará de forma centralizada desde game.js
  }
  draw(ctx) {
    if (this.image) {
      ctx.drawImage(this.image, this.x, this.y, this.size, this.size);
    } else {
      ctx.fillStyle = "gold";
      ctx.beginPath();
      ctx.arc(this.x + this.size / 2, this.y + this.size / 2, this.size / 2, 0, Math.PI * 2);
      ctx.fill();
    }
  }
}
