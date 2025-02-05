class Enemy {
  constructor(x, y, width, height, originalX, range, speed) {
    this.x = x;
    this.y = y;
    this.width = width;
    this.height = height;
    this.originalX = originalX;
    this.range = range;
    this.speed = speed;
    // La imagen se asignará de forma centralizada desde game.js
  }
  update() {
    this.x += this.speed;
    if (this.x < this.originalX || this.x > this.originalX + this.range) {
      this.speed *= -1;
    }
  }
  draw(ctx) {
    if (this.image) {
      ctx.drawImage(this.image, this.x, this.y, this.width, this.height);
    } else {
      ctx.fillStyle = "purple";
      ctx.fillRect(this.x, this.y, this.width, this.height);
    }
  }
}
