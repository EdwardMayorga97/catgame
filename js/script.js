// Función auxiliar para comprobar la superposición de dos rectángulos
function isOverlapping(rect1, rect2) {
  return (
    rect1.x < rect2.x + rect2.width &&
    rect1.x + rect1.width > rect2.x &&
    rect1.y < rect2.y + rect2.height &&
    rect1.y + rect1.height > rect2.y
  );
}

// Función auxiliar para comprobar si un rectángulo se solapa con algún objeto de un arreglo
// Los objetos pueden tener propiedades "width"/"height" o "size"
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

// Clase principal del juego
class Game {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.width = canvas.width;
    this.height = canvas.height;

    // Elementos del nivel
    this.platforms = [];
    this.obstacles = []; // Obstáculos rojos (que reinician el nivel)
    this.barriers = [];  // Barreras (obstáculos azules que bloquean el paso)
    this.cookies = [];
    this.enemies = [];
    this.finish = null; // El gatico meta

    // Dimensiones del nivel (más largo a medida que aumenta el nivel)
    this.levelWidth = this.width;

    // Jugador
    this.player = new Player(50, this.height - 50 - 40);

    // Configuración física y de controles
    this.gravity = 0.5;
    this.keys = {};

    // Progreso global
    this.kittyCount = 0;   // Gaticos recolectados (para pasar de nivel)
    this.cookieCount = 0;  // Cookies recolectadas
    this.level = 1;

    // Variable para el desplazamiento de la cámara
    this.cameraX = 0;

    // Generar el primer nivel
    this.generateLevel();

    this.setupListeners();
    this.lastTime = 0;
    requestAnimationFrame(this.gameLoop.bind(this));
  }

  // Genera el nivel actual (una sola vez) según this.level
  generateLevel() {
    // La longitud del nivel aumenta con el nivel (más largo y con más retos)
    this.levelWidth = this.width + this.level * 300;

    // Reiniciar arrays (el mapa se genera solo una vez; al reiniciar por muerte se conserva)
    this.platforms = [];
    this.obstacles = [];
    this.barriers = [];
    this.cookies = [];
    this.enemies = [];

    // 1. Suelo: una plataforma que recorre todo el nivel
    this.platforms.push(new Platform(0, this.height - 50, this.levelWidth, 50));

    // 2. Generar plataformas flotantes a lo largo del nivel.
    let lastX = 50;
    while (lastX < this.levelWidth - 200) {
      // Separación y ancho aleatorios para la plataforma
      let gap = Math.random() * 100 + 100;
      let platformWidth = Math.random() * 50 + 80; // entre 80 y 130
      let x = lastX + gap;
      if (x + platformWidth > this.levelWidth - 50) {
        x = this.levelWidth - platformWidth - 50;
      }
      // Altura entre 50 y 150 sobre el suelo
      let y = this.height - 50 - (Math.random() * 100 + 50);

      // Con cierta probabilidad (si nivel >= 2) la plataforma será móvil
      let platform;
      if (this.level >= 2 && Math.random() < 0.3) {
        // Rango de movimiento aleatorio (entre 50 y 100 píxeles) y velocidad
        let range = Math.random() * 50 + 50;
        let speed = (Math.random() * 1 + 0.5) * (Math.random() < 0.5 ? 1 : -1);
        platform = new MovingPlatform(x, y, platformWidth, 15, x, range, speed);
      } else {
        platform = new Platform(x, y, platformWidth, 15);
      }
      this.platforms.push(platform);
      lastX = x;
      
      // 2.1. Colocar cookies (coleccionables) en algunas plataformas (probabilidad 50%)
      if (platform.y < this.height - 50 && Math.random() < 0.5) {
        let cookieX = platform.x + Math.random() * (platform.width - 15);
        let cookieY = platform.y - 15; // justo encima de la plataforma
        let cookieRect = { x: cookieX, y: cookieY, width: 15, height: 15 };
        // Solo agregar la cookie si no se superpone con enemigos o barreras (que se colocarán también)
        if (!overlapsAny(cookieRect, this.enemies) && !overlapsAny(cookieRect, this.barriers)) {
          this.cookies.push(new Cookie(cookieX, cookieY));
        }
      }

      // 2.2. En niveles de dificultad mayor (>=2) puede aparecer un enemigo en la plataforma (30% de prob.)
      if (this.level >= 2 && platform.y < this.height - 50 && Math.random() < 0.3) {
        let enemyX = platform.x + Math.random() * (platform.width - 30);
        let enemyY = platform.y - 30; // se asienta sobre la plataforma
        let enemyRange = platform.width - 30;
        let enemySpeed = (Math.random() * 1 + 0.5) * (Math.random() < 0.5 ? 1 : -1);
        let enemyRect = { x: enemyX, y: enemyY, width: 30, height: 30 };
        if (!overlapsAny(enemyRect, this.cookies)) {
          this.enemies.push(new Enemy(enemyX, enemyY, 30, 30, enemyX, enemyRange, enemySpeed));
        }
      }

      // 2.3. Colocar obstáculos rojos en algunas plataformas flotantes (probabilidad 50%)
      if (platform.y < this.height - 50 && Math.random() < 0.5) {
        let obsWidth = 30;
        let obsHeight = 30;
        let obsX = platform.x + Math.random() * (platform.width - obsWidth);
        let obsY = platform.y - obsHeight;
        this.obstacles.push(new Obstacle(obsX, obsY, obsWidth, obsHeight));
      }

      // 2.4. Colocar barreras (obstáculos azules que bloquean el paso)
      // Se generan con menor probabilidad para no saturar el nivel
      if (Math.random() < 0.3) {
        let barWidth = 20;
        let barHeight = 40;
        // Si la barrera se coloca en el suelo, se evita que bloquee totalmente el camino
        let barX = platform === this.platforms[0]
                   ? platform.x + Math.random() * (platform.width - barWidth - 30) + 15
                   : platform.x + Math.random() * (platform.width - barWidth);
        let barY = platform === this.platforms[0]
                   ? this.height - 50 - barHeight
                   : platform.y - barHeight;
        this.barriers.push(new Barrier(barX, barY, barWidth, barHeight));
      }
    }

    // 3. Colocar el finish (el gatico meta) en la última plataforma flotante
    let candidatePlatforms = this.platforms.filter(p => p.y < this.height - 50);
    let targetPlatform = candidatePlatforms.length > 0 ? candidatePlatforms[candidatePlatforms.length - 1] : this.platforms[0];
    let finishX = targetPlatform.x + targetPlatform.width / 2 - 10;
    let finishY = targetPlatform.y - 20;
    this.finish = new Finish(finishX, finishY);

    // 3.1. Ajustar la posición del finish para evitar superposiciones con cookies, enemigos o barreras
    let attempts = 0;
    while (
      (overlapsAny({ x: this.finish.x, y: this.finish.y, width: this.finish.size, height: this.finish.size }, this.cookies) ||
       overlapsAny({ x: this.finish.x, y: this.finish.y, width: this.finish.size, height: this.finish.size }, this.enemies) ||
       overlapsAny({ x: this.finish.x, y: this.finish.y, width: this.finish.size, height: this.finish.size }, this.barriers)
      ) && attempts < 10
    ) {
      finishX += (Math.random() - 0.5) * 20;
      finishX = Math.max(targetPlatform.x, Math.min(finishX, targetPlatform.x + targetPlatform.width - this.finish.size));
      this.finish.x = finishX;
      attempts++;
    }

    // 4. Reiniciar la posición del jugador al inicio del nivel
    this.resetPlayer();
    // Reiniciar la cámara
    this.cameraX = 0;
  }

  // Configura eventos de teclado
  setupListeners() {
    window.addEventListener("keydown", (e) => {
      this.keys[e.code] = true;
    });
    window.addEventListener("keyup", (e) => {
      this.keys[e.code] = false;
    });
  }

  // Reinicia la posición del jugador (cuando pierde) sin cambiar el mapa actual
  resetPlayer() {
    this.player.x = 50;
    this.player.y = this.height - 50 - this.player.height;
    this.player.vy = 0;
    // Reiniciar la cámara
    this.cameraX = 0;
  }

  // Bucle principal del juego
  gameLoop(timestamp) {
    const deltaTime = timestamp - this.lastTime;
    this.lastTime = timestamp;
    this.update(deltaTime);
    this.draw();
    requestAnimationFrame(this.gameLoop.bind(this));
  }

  // Actualiza la lógica del juego
  update(deltaTime) {
    // Almacenar la posición horizontal previa para resolver colisiones con barreras
    const prevX = this.player.x;

    // Movimiento lateral del jugador
    if (this.keys["ArrowLeft"] || this.keys["KeyA"]) {
      this.player.move(-3);
    }
    if (this.keys["ArrowRight"] || this.keys["KeyD"]) {
      this.player.move(3);
    }
    // Salto (si no está ya saltando)
    if ((this.keys["ArrowUp"] || this.keys["KeyW"] || this.keys["Space"]) && !this.player.jumping) {
      this.player.jump();
    }

    // Aplicar gravedad
    this.player.vy += this.gravity;
    this.player.y += this.player.vy;

    // Actualizar plataformas móviles (si las hay)
    this.platforms.forEach(p => {
      if (p.update) {
        p.update();
      }
    });

    // Actualizar enemigos
    this.enemies.forEach(enemy => enemy.update());

    // Comprobar colisión del jugador con las plataformas (para aterrizar)
    let onPlatform = false;
    for (let platform of this.platforms) {
      if (
        this.player.x + this.player.width > platform.x &&
        this.player.x < platform.x + platform.width &&
        this.player.y + this.player.height > platform.y &&
        this.player.y + this.player.height - this.player.vy <= platform.y
      ) {
        // El jugador aterriza sobre la plataforma
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
    if (this.player.x < 0) this.player.x = 0;
    if (this.player.x + this.player.width > this.levelWidth)
      this.player.x = this.levelWidth - this.player.width;

    // Comprobar colisión con obstáculos rojos (que reinician el nivel)
    for (let obstacle of this.obstacles) {
      if (
        isOverlapping(
          { x: this.player.x, y: this.player.y, width: this.player.width, height: this.player.height },
          { x: obstacle.x, y: obstacle.y, width: obstacle.width, height: obstacle.height }
        )
      ) {
        console.log("Choque con obstáculo. Reiniciando nivel...");
        this.resetPlayer();
        return;
      }
    }

    // Comprobar colisión con enemigos (que reinician el nivel)
    for (let enemy of this.enemies) {
      if (
        isOverlapping(
          { x: this.player.x, y: this.player.y, width: this.player.width, height: this.player.height },
          { x: enemy.x, y: enemy.y, width: enemy.width, height: enemy.height }
        )
      ) {
        console.log("Choque con enemigo. Reiniciando nivel...");
        this.resetPlayer();
        return;
      }
    }

    // Resolver colisiones con barreras (obstáculos azules) sin reiniciar el nivel
    // Se utiliza la posición horizontal previa (prevX) para determinar de qué lado viene el jugador
    for (let barrier of this.barriers) {
      if (
        isOverlapping(
          { x: this.player.x, y: this.player.y, width: this.player.width, height: this.player.height },
          { x: barrier.x, y: barrier.y, width: barrier.width, height: barrier.height }
        )
      ) {
        // Si el jugador venía de la izquierda, colócalo a la izquierda de la barrera;
        // si venía de la derecha, a la derecha; de lo contrario, revierte a prevX.
        if (prevX + this.player.width <= barrier.x) {
          this.player.x = barrier.x - this.player.width;
        } else if (prevX >= barrier.x + barrier.width) {
          this.player.x = barrier.x + barrier.width;
        } else {
          this.player.x = prevX;
        }
      }
    }

    // Comprobar colisión con cookies (coleccionables)
    for (let i = this.cookies.length - 1; i >= 0; i--) {
      let cookie = this.cookies[i];
      if (
        this.player.x < cookie.x + cookie.size &&
        this.player.x + this.player.width > cookie.x &&
        this.player.y < cookie.y + cookie.size &&
        this.player.y + this.player.height > cookie.y
      ) {
        // Se recoge la cookie
        this.cookies.splice(i, 1);
        this.cookieCount++;
        console.log("¡Cookie recogida! Total: " + this.cookieCount);
      }
    }

    // Comprobar colisión con el finish (gatico meta)
    if (
      this.player.x < this.finish.x + this.finish.size &&
      this.player.x + this.player.width > this.finish.x &&
      this.player.y < this.finish.y + this.finish.size &&
      this.player.y + this.player.height > this.finish.y
    ) {
      console.log("¡Gatico encontrado! Nivel completado.");
      this.kittyCount++;
      // Al completar el nivel se genera un mapa nuevo
      this.level++;
      this.generateLevel();
      return;
    }

    // Actualizar la cámara para centrar al jugador
    this.cameraX = this.player.x - this.width / 2;
    if (this.cameraX < 0) this.cameraX = 0;
    if (this.cameraX > this.levelWidth - this.width)
      this.cameraX = this.levelWidth - this.width;
  }

  // Dibuja el mundo y el HUD
  draw() {
    // Limpiar el canvas
    this.ctx.clearRect(0, 0, this.width, this.height);

    // Guardar contexto y aplicar traslación (cámara)
    this.ctx.save();
    this.ctx.translate(-this.cameraX, 0);

    // Dibujar plataformas
    this.platforms.forEach(p => p.draw(this.ctx));

    // Dibujar obstáculos rojos
    this.obstacles.forEach(o => o.draw(this.ctx));

    // Dibujar barreras
    this.barriers.forEach(b => b.draw(this.ctx));

    // Dibujar cookies
    this.cookies.forEach(c => c.draw(this.ctx));

    // Dibujar enemigos
    this.enemies.forEach(e => e.draw(this.ctx));

    // Dibujar el finish (gatico meta)
    this.finish.draw(this.ctx);

    // Dibujar al jugador
    this.player.draw(this.ctx);

    // Restaurar el contexto para dibujar el HUD sin traslación
    this.ctx.restore();

    // HUD
    this.ctx.fillStyle = "white";
    this.ctx.font = "16px Arial";
    this.ctx.fillText("Nivel: " + this.level, 10, 20);
    this.ctx.fillText("Gaticos: " + this.kittyCount, 10, 40);
    this.ctx.fillText("Cookies: " + this.cookieCount, 10, 60);
  }
}

// Clase para el jugador (gato)
class Player {
  constructor(x, y) {
    this.x = x;
    this.y = y;
    this.width = 40;
    this.height = 40;
    this.vy = 0;
    this.jumping = false;
  }
  move(dx) {
    this.x += dx;
  }
  jump() {
    this.vy = -10;
    this.jumping = true;
  }
  draw(ctx) {
    ctx.fillStyle = "orange";
    ctx.fillRect(this.x, this.y, this.width, this.height);
    // Detalles (ojos simples)
    ctx.fillStyle = "black";
    ctx.fillRect(this.x + 10, this.y + 10, 5, 5);
    ctx.fillRect(this.x + 25, this.y + 10, 5, 5);
  }
}

// Clase para plataformas estáticas
class Platform {
  constructor(x, y, width, height) {
    this.x = x;
    this.y = y;
    this.width = width;
    this.height = height;
  }
  draw(ctx) {
    ctx.fillStyle = "#654321";
    ctx.fillRect(this.x, this.y, this.width, this.height);
  }
}

// Clase para plataformas móviles (extiende de Platform)
class MovingPlatform extends Platform {
  constructor(x, y, width, height, originalX, range, speed) {
    super(x, y, width, height);
    this.originalX = originalX; // posición de inicio
    this.range = range;         // desplazamiento máximo
    this.speed = speed;
  }
  update() {
    this.x += this.speed;
    if (this.x < this.originalX || this.x > this.originalX + this.range) {
      this.speed *= -1;
    }
  }
  // Se utiliza el mismo método draw que en Platform
}

// Clase para obstáculos rojos (que reinician el nivel)
class Obstacle {
  constructor(x, y, width, height) {
    this.x = x;
    this.y = y;
    this.width = width;
    this.height = height;
  }
  draw(ctx) {
    ctx.fillStyle = "red";
    ctx.fillRect(this.x, this.y, this.width, this.height);
  }
}

// Clase para barreras (obstáculos azules que bloquean el paso sin hacerte perder)
class Barrier {
  constructor(x, y, width, height) {
    this.x = x;
    this.y = y;
    this.width = width;
    this.height = height;
  }
  draw(ctx) {
    ctx.fillStyle = "blue";
    ctx.fillRect(this.x, this.y, this.width, this.height);
  }
}

// Clase para las cookies (coleccionables)
class Cookie {
  constructor(x, y) {
    this.x = x;
    this.y = y;
    this.size = 15;
  }
  draw(ctx) {
    ctx.fillStyle = "gold";
    ctx.beginPath();
    ctx.arc(this.x + this.size / 2, this.y + this.size / 2, this.size / 2, 0, Math.PI * 2);
    ctx.fill();
  }
}

// Clase para enemigos móviles
class Enemy {
  constructor(x, y, width, height, originalX, range, speed) {
    this.x = x;
    this.y = y;
    this.width = width;
    this.height = height;
    this.originalX = originalX;
    this.range = range;
    this.speed = speed;
  }
  update() {
    this.x += this.speed;
    if (this.x < this.originalX || this.x > this.originalX + this.range) {
      this.speed *= -1;
    }
  }
  draw(ctx) {
    ctx.fillStyle = "purple";
    ctx.fillRect(this.x, this.y, this.width, this.height);
  }
}

// Clase para el finish (gatico meta)
class Finish {
  constructor(x, y) {
    this.x = x;
    this.y = y;
    this.size = 20;
  }
  draw(ctx) {
    ctx.fillStyle = "pink";
    ctx.fillRect(this.x, this.y, this.size, this.size);
    // Dibujar orejas sencillas
    ctx.fillStyle = "black";
    ctx.fillRect(this.x - 4, this.y, 4, 4);
    ctx.fillRect(this.x + this.size, this.y, 4, 4);
  }
}

// Iniciar el juego
const canvas = document.getElementById("gameCanvas");
const game = new Game(canvas);
