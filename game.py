import pygame
import math
import random

# Window dimensions
WIDTH, HEIGHT = 800, 600

# Colors
WHITE = (255, 255, 255)
RED = (255, 0, 0)

class Icosagon:
    def __init__(self):
        self.center_x = WIDTH // 2
        self.center_y = HEIGHT // 2
        self.radius = 200
        self.angle = 0
        self.vertices = []
        self.sides = 20

    def update(self):
        self.angle += 1
        self.vertices = []
        for i in range(self.sides):
            angle = self.angle + i * 360 / self.sides
            x = self.center_x + self.radius * math.cos(math.radians(angle))
            y = self.center_y + self.radius * math.sin(math.radians(angle))
            self.vertices.append((x, y))

    def draw(self, screen):
        for i in range(self.sides):
            p1 = self.vertices[i]
            p2 = self.vertices[(i + 1) % self.sides]
            pygame.draw.line(screen, WHITE, p1, p2, 2)
class Ball:
    def __init__(self, icosagon):
        angle = random.uniform(0, 360)
        # Use the icosagon's incircle radius = R * cos(π / n)
        radius = random.uniform(0, icosagon.radius * math.cos(math.radians(180 / icosagon.sides)))
        self.x = icosagon.center_x + radius * math.cos(math.radians(angle))
        self.y = icosagon.center_y + radius * math.sin(math.radians(angle))
        self.vx = random.uniform(-5, 5)
        self.vy = random.uniform(-5, 5)
        self.radius = 10
        self.gravity = 0.1

    def update(self):
        self.vy += self.gravity
        self.x += self.vx
        self.y += self.vy

        # Bounce off window edges
        if self.x - self.radius < 0 or self.x + self.radius > WIDTH:
            self.vx *= -1
        if self.y - self.radius < 0 or self.y + self.radius > HEIGHT:
            self.vy *= -0.9  # lose some energy on vertical bounce

    def draw(self, screen):
        pygame.draw.circle(screen, RED, (int(self.x), int(self.y)), self.radius)

def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()

    icosagon = Icosagon()
    balls = [Ball(icosagon) for _ in range(10)]

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        screen.fill((0, 0, 0))

        icosagon.update()
        icosagon.draw(screen)

        for ball in balls:
            ball.update()
            ball.draw(screen)

            # bounce off icosagon
            for i in range(icosagon.sides):
                p1 = icosagon.vertices[i]
                p2 = icosagon.vertices[(i + 1) % icosagon.sides]
                dx = p2[0] - p1[0]
                dy = p2[1] - p1[1]
                dist = math.hypot(dx, dy)
                t = ((ball.x - p1[0]) * dx + (ball.y - p1[1]) * dy) / (dist ** 2)
                t = max(0, min(1, t))
                nearest_x = p1[0] + t * dx
                nearest_y = p1[1] + t * dy
                dist_to_line = math.hypot(ball.x - nearest_x, ball.y - nearest_y)
                if dist_to_line < ball.radius:
                    ball.vx, ball.vy = -ball.vx, -ball.vy

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()

if __name__ == "__main__":
    main()
