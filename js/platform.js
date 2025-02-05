class Platform {
  constructor(x, y, width, height) {
    this.x = x;
    this.y = y;
    this.width = width;
    this.height = height;
    // Si usas sprite para plataformas, se asignará desde game.js
  }
  draw(ctx) {
    // Si hay imagen asignada se usa, de lo contrario se dibuja un rectángulo
    if (this.image) {
      ctx.drawImage(this.image, this.x, this.y, this.width, this.height);
    } else {
      ctx.fillStyle = "#654321";
      ctx.fillRect(this.x, this.y, this.width, this.height);
    }
  }
}

class MovingPlatform extends Platform {
  constructor(x, y, width, height, originalX, range, speed) {
    super(x, y, width, height);
    this.originalX = originalX; // Posición inicial
    this.range = range;         // Desplazamiento máximo
    this.speed = speed;
  }
  update() {
    this.x += this.speed;
    if (this.x < this.originalX || this.x > this.originalX + this.range) {
      this.speed *= -1;
    }
  }
}
