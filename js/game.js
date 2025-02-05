class Game {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.width = canvas.width;
    this.height = canvas.height;
    
    // Elementos del nivel
    this.platforms = [];
    this.obstacles = [];
    this.barriers = [];
    this.cookies = [];
    this.enemies = [];
    this.finish = null;
    
    // Dimensiones del nivel (se extiende con cada nivel)
    this.levelWidth = this.width;
    
    // Jugador
    this.player = new Player(50, this.height - 50 - 40);
    
    // Configuración física y controles
    this.gravity = 0.15;
    this.keys = {};
    
    // Progreso
    this.kittyCount = 0;
    this.cookieCount = 0;
    this.level = 1;
    
    // Cámara
    this.cameraX = 0;
    
    this.generateLevel();
    this.setupListeners();
    this.lastTime = 0;
    requestAnimationFrame(this.gameLoop.bind(this));
  }
  
  generateLevel() {
    // El nivel se hace más largo con cada nivel
    this.levelWidth = this.width + this.level * 300;
    
    // Reiniciar arrays
    this.platforms = [];
    this.obstacles = [];
    this.barriers = [];
    this.cookies = [];
    this.enemies = [];
    
    // 1. Plataforma base (suelo)
    this.platforms.push(new Platform(0, this.height - 50, this.levelWidth, 50));
    
    // 2. Generar plataformas secuenciales con simetría y conectividad
    let lastPlatform = this.platforms[0];
    const numPlatforms = Math.floor(Math.random() * 4) + 5; // Entre 5 y 8 plataformas
    for (let i = 0; i < numPlatforms; i++) {
      // Separación horizontal entre 100 y 250 píxeles
      const gap = Math.random() * 150 + 100;
      // Ancho de la plataforma entre 80 y 130 píxeles
      const platformWidth = Math.random() * 50 + 80;
      let x = lastPlatform.x + gap;
      if (x + platformWidth > this.levelWidth - 50) {
        x = this.levelWidth - platformWidth - 50;
      }
      // Variación vertical limitada a ±50 píxeles respecto a la anterior
      const minY = Math.max(50, lastPlatform.y - 50);
      const maxY = Math.min(this.height - 150, lastPlatform.y + 50);
      const y = Math.random() * (maxY - minY) + minY;
  
      // Crear plataforma; si nivel >= 2, posibilidad de plataforma móvil (30%)
      let platform;
      if (this.level >= 2 && Math.random() < 0.3) {
        const range = Math.random() * 50 + 50;
        const speed = (Math.random() * 1 + 0.5) * (Math.random() < 0.5 ? 1 : -1);
        platform = new MovingPlatform(x, y, platformWidth, 15, x, range, speed);
      } else {
        platform = new Platform(x, y, platformWidth, 15);
      }
      this.platforms.push(platform);
      lastPlatform = platform;
  
      // 2.1. Generar cookies en la plataforma (si es adecuada)
      if (y < this.height - 100 && Math.random() < 0.5) {
        const cookieX = x + Math.random() * (platformWidth - 15);
        const cookieY = y - 15;
        this.cookies.push(new Cookie(cookieX, cookieY));
      }
  
      // 2.2. Generar enemigos (nivel >= 2 y plataforma adecuada)
      if (this.level >= 2 && y < this.height - 100 && Math.random() < 0.3) {
        const enemyX = x + Math.random() * (platformWidth - 30);
        const enemyY = y - 30;
        const enemyRange = platformWidth - 30;
        const enemySpeed = (Math.random() * 1 + 0.5) * (Math.random() < 0.5 ? 1 : -1);
        this.enemies.push(new Enemy(enemyX, enemyY, 30, 30, enemyX, enemyRange, enemySpeed));
      }
  
      // 2.3. Generar obstáculos rojos (evitando bloquear el paso)
      if (y < this.height - 100 && Math.random() < 0.5) {
        const obsWidth = 30;
        const obsHeight = 30;
        let obsX = x + Math.random() * (platformWidth - obsWidth);
        let obsY = y - obsHeight;
        if (obsY < y - 30) {
          obsY = y - 30;
        }
        this.obstacles.push(new Obstacle(obsX, obsY, obsWidth, obsHeight));
      }
  
      // 2.4. Generar barreras (azules) que bloqueen el paso sin hacerte perder
      if (Math.random() < 0.3) {
        const barWidth = 20;
        const barHeight = 40;
        let barX;
        if (i === 0) {
          barX = x + Math.random() * (platformWidth - barWidth - 30) + 15;
        } else {
          barX = x + Math.random() * (platformWidth - barWidth);
        }
        const barY = (i === 0) ? this.height - 50 - barHeight : y - barHeight;
        this.barriers.push(new Barrier(barX, barY, barWidth, barHeight));
      }
    }
  
    // 3. Colocar el finish (gatico meta) en la última plataforma generada
    const targetPlatform = lastPlatform;
    let finishX = targetPlatform.x + targetPlatform.width / 2 - 10;
    let finishY = targetPlatform.y - 20;
    this.finish = new Finish(finishX, finishY);
  
    // Verificar que el finish no se solape con cookies, barreras o esté demasiado cerca de enemigos
    const minMargin = 50; // Margen mínimo deseado respecto a los enemigos
    function isTooCloseToEnemies(finish, enemies, margin) {
      for (let enemy of enemies) {
        let expandedEnemy = {
          x: enemy.x - margin,
          y: enemy.y - margin,
          width: enemy.width + margin * 2,
          height: enemy.height + margin * 2
        };
        if (isOverlapping(
          { x: finish.x, y: finish.y, width: finish.size, height: finish.size },
          expandedEnemy
        )) {
          return true;
        }
      }
      return false;
    }
  
    let attempts = 0;
    while (
      (overlapsAny({ x: this.finish.x, y: this.finish.y, width: this.finish.size, height: this.finish.size }, this.cookies) ||
       overlapsAny({ x: this.finish.x, y: this.finish.y, width: this.finish.size, height: this.finish.size }, this.barriers) ||
       isTooCloseToEnemies(this.finish, this.enemies, minMargin)
      ) && attempts < 10
    ) {
      finishX += (Math.random() - 0.5) * 20;
      finishX = Math.max(targetPlatform.x, Math.min(finishX, targetPlatform.x + targetPlatform.width - this.finish.size));
      this.finish.x = finishX;
      attempts++;
    }
  
    this.resetPlayer();
    this.cameraX = 0;
  }
  
  setupListeners() {
    window.addEventListener("keydown", (e) => { this.keys[e.code] = true; });
    window.addEventListener("keyup", (e) => { this.keys[e.code] = false; });
  }
  
  resetPlayer() {
    this.player.x = 50;
    this.player.y = this.height - 50 - this.player.height;
    this.player.vy = 0;
    this.cameraX = 0;
  }
  
  gameLoop(timestamp) {
    const deltaTime = timestamp - this.lastTime;
    this.lastTime = timestamp;
    this.update(deltaTime);
    this.draw();
    requestAnimationFrame(this.gameLoop.bind(this));
  }
  
  update(deltaTime) {
    // Guardar la posición previa del jugador (horizontal y vertical)
    const prevX = this.player.x;
    const prevY = this.player.y;
  
    // Parámetros para el movimiento suave
    const acceleration = 0.25; // Aceleración al presionar las teclas
    const friction = 0.85;     // Fricción para reducir la velocidad si no se presionan teclas
    const maxSpeed = 2.5;      // Velocidad máxima horizontal
  
    // Procesar controles para movimiento horizontal:
    if (this.keys["ArrowLeft"] || this.keys["KeyA"]) {
      this.player.vx -= acceleration;
    }
    if (this.keys["ArrowRight"] || this.keys["KeyD"]) {
      this.player.vx += acceleration;
    }
    if (!this.keys["ArrowLeft"] && !this.keys["KeyA"] && !this.keys["ArrowRight"] && !this.keys["KeyD"]) {
      this.player.vx *= friction;
    }
    if (this.player.vx > maxSpeed) {
      this.player.vx = maxSpeed;
    } else if (this.player.vx < -maxSpeed) {
      this.player.vx = -maxSpeed;
    }
    // Actualizar la posición horizontal
    this.player.x += this.player.vx;
  
    // Procesar salto:
    if ((this.keys["ArrowUp"] || this.keys["KeyW"] || this.keys["Space"]) && !this.player.jumping) {
      this.player.jump();
    }
  
    // Aplicar gravedad a la velocidad vertical y actualizar la posición vertical
    this.player.vy += this.gravity;
    this.player.y += this.player.vy;
  
    // Actualizar plataformas móviles y enemigos
    this.platforms.forEach(p => { if (p.update) { p.update(); } });
    this.enemies.forEach(enemy => enemy.update());
  
    // Resolver colisiones con plataformas (para aterrizar)
    let onPlatform = false;
    for (let platform of this.platforms) {
      if (
        this.player.x + this.player.width > platform.x &&
        this.player.x < platform.x + platform.width &&
        this.player.y + this.player.height > platform.y &&
        this.player.y + this.player.height - this.player.vy <= platform.y
      ) {
        this.player.y = platform.y - this.player.height;
        this.player.vy = 0;
        onPlatform = true;
        this.player.jumping = false;
      }
    }
    if (!onPlatform && this.player.y + this.player.height < this.height) {
      this.player.jumping = true;
    }
  
    // Limitar al jugador dentro del mundo
    if (this.player.x < 0) {
      this.player.x = 0;
    }
    if (this.player.x + this.player.width > this.levelWidth) {
      this.player.x = this.levelWidth - this.player.width;
    }
  
    // Colisiones con obstáculos rojos
    for (let obstacle of this.obstacles) {
      if (isOverlapping(
        { x: this.player.x, y: this.player.y, width: this.player.width, height: this.player.height },
        { x: obstacle.x, y: obstacle.y, width: obstacle.width, height: obstacle.height }
      )) {
        console.log("Choque con obstáculo. Reiniciando nivel...");
        this.resetPlayer();
        return;
      }
    }
  
    // Colisiones con enemigos
    for (let enemy of this.enemies) {
      if (isOverlapping(
        { x: this.player.x, y: this.player.y, width: this.player.width, height: this.player.height },
        { x: enemy.x, y: enemy.y, width: enemy.width, height: enemy.height }
      )) {
        console.log("Choque con enemigo. Reiniciando nivel...");
        this.resetPlayer();
        return;
      }
    }
  
    // Resolver colisiones con barreras (azules)
    for (let barrier of this.barriers) {
      if (isOverlapping(
        { x: this.player.x, y: this.player.y, width: this.player.width, height: this.player.height },
        { x: barrier.x, y: barrier.y, width: barrier.width, height: barrier.height }
      )) {
        // Si el jugador venía desde arriba, se le permite aterrizar sobre la barrera
        if (prevY + this.player.height <= barrier.y + 5) {
          this.player.y = barrier.y - this.player.height;
          this.player.vy = 0;
          this.player.jumping = false;
        } else {
          // Resolución lateral de la colisión
          if (prevX + this.player.width <= barrier.x) {
            this.player.x = barrier.x - this.player.width;
          } else if (prevX >= barrier.x + barrier.width) {
            this.player.x = barrier.x + barrier.width;
          } else {
            this.player.x = prevX;
          }
        }
      }
    }
  
    // Colisiones con cookies
    for (let i = this.cookies.length - 1; i >= 0; i--) {
      let cookie = this.cookies[i];
      if (
        this.player.x < cookie.x + cookie.size &&
        this.player.x + this.player.width > cookie.x &&
        this.player.y < cookie.y + cookie.size &&
        this.player.y + this.player.height > cookie.y
      ) {
        this.cookies.splice(i, 1);
        this.cookieCount++;
        console.log("¡Cookie recogida! Total: " + this.cookieCount);
      }
    }
  
    // Colisión con el finish (gatico meta)
    if (
      this.player.x < this.finish.x + this.finish.size &&
      this.player.x + this.player.width > this.finish.x &&
      this.player.y < this.finish.y + this.finish.size &&
      this.player.y + this.player.height > this.finish.y
    ) {
      console.log("¡Gatico encontrado! Nivel completado.");
      this.kittyCount++;
      this.level++;
      this.generateLevel();
      return;
    }
  
    // Actualizar la cámara para centrar al jugador
    this.cameraX = this.player.x - this.width / 2;
    if (this.cameraX < 0) {
      this.cameraX = 0;
    }
    if (this.cameraX > this.levelWidth - this.width) {
      this.cameraX = this.levelWidth - this.width;
    }
  }
  
  draw() {
    this.ctx.clearRect(0, 0, this.width, this.height);
    
    this.ctx.save();
    this.ctx.translate(-this.cameraX, 0);
    
    this.platforms.forEach(p => p.draw(this.ctx));
    this.obstacles.forEach(o => o.draw(this.ctx));
    this.barriers.forEach(b => b.draw(this.ctx));
    this.cookies.forEach(c => c.draw(this.ctx));
    this.enemies.forEach(e => e.draw(this.ctx));
    this.finish.draw(this.ctx);
    this.player.draw(this.ctx);
    
    this.ctx.restore();
    
    // Dibujar HUD
    this.ctx.fillStyle = "white";
    this.ctx.font = "16px Arial";
    this.ctx.fillText("Nivel: " + this.level, 10, 20);
    this.ctx.fillText("Gaticos: " + this.kittyCount, 10, 40);
    this.ctx.fillText("Cookies: " + this.cookieCount, 10, 60);
  }
}

/* 
  Asignación centralizada de los sprites a través de game.js.
  De esta forma solo necesitas modificar las rutas en el objeto spritePaths.
*/
const spritePaths = {
  player: "images/player.png",
  enemy: "images/enemy.png",
  kitty: "images/kitty.png",
  cookie: "images/cookie.png",
  obstacle: "images/obstacle.png",
  barrier: "images/barrier.png",
  platform: "images/platform.png"
};

// Asignar sprites a los prototipos
Player.prototype.image = new Image();
Player.prototype.image.src = spritePaths.player;

Enemy.prototype.image = new Image();
Enemy.prototype.image.src = spritePaths.enemy;

Finish.prototype.image = new Image();
Finish.prototype.image.src = spritePaths.kitty;

Cookie.prototype.image = new Image();
Cookie.prototype.image.src = spritePaths.cookie;

Obstacle.prototype.image = new Image();
Obstacle.prototype.image.src = spritePaths.obstacle;

Barrier.prototype.image = new Image();
Barrier.prototype.image.src = spritePaths.barrier;

Platform.prototype.image = new Image();
Platform.prototype.image.src = spritePaths.platform;
