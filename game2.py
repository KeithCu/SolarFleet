import pygame
import math
import random

# Window dimensions
WIDTH, HEIGHT = 800, 600

# Colors
BLACK = (0, 0, 0)

# Perspective parameters for pseudo-3D drawing
FOCAL_LENGTH = 500  # adjust for more/less perspective
TILT_ANGLE = math.radians(30)  # fixed tilt for the polygon

def project_3d(x, y, z):
    """
    Simple perspective projection.
    (x, y, z) is in our world coordinates.
    (0,0) is taken as the center of projection.
    """
    factor = FOCAL_LENGTH / (FOCAL_LENGTH + z)
    return (x * factor, y * factor)

class Icosagon:
    def __init__(self):
        self.center_x = WIDTH // 2
        self.center_y = HEIGHT // 2
        self.radius = 200
        self.angle = 0
        self.sides = 20
        self.vertices = []
        self.y_rotation = 0  # Additional rotation about y-axis for enhanced 3D effect

    def update(self):
        self.angle = (self.angle + 1) % 360
        self.y_rotation = (self.y_rotation + 0.5) % 360  # slowly spin around the y-axis
        self.vertices = []
        for i in range(self.sides):
            theta = self.angle + i * 360 / self.sides
            rad = math.radians(theta)
            x = self.center_x + self.radius * math.cos(rad)
            y = self.center_y + self.radius * math.sin(rad)
            self.vertices.append((x, y))

    def get_projected_vertices(self):
        """
        Upgraded to apply both a y-axis rotation and an x-axis tilt.
        """
        projected = []
        # Pre-calculate the rotation angle for y-axis.
        y_rot_angle = math.radians(self.y_rotation)
        tilt = TILT_ANGLE  # fixed tilt angle (already in radians)
        for (x, y) in self.vertices:
            # Convert to coordinates relative to screen center.
            rx = x - WIDTH / 2
            ry = y - HEIGHT / 2
            rz = 0  # original flat polygon

            # Rotate about the y-axis.
            #   x1 = rx*cos(y_angle) + rz*sin(y_angle)
            #   z1 = -rx*sin(y_angle) + rz*cos(y_angle)
            x1 = rx * math.cos(y_rot_angle) + rz * math.sin(y_rot_angle)
            z1 = -rx * math.sin(y_rot_angle) + rz * math.cos(y_rot_angle)

            # Now, rotate about the x-axis by the tilt.
            #   y2 = ry*cos(tilt) - z1*sin(tilt)
            #   z2 = ry*sin(tilt) + z1*cos(tilt)
            y2 = ry * math.cos(tilt) - z1 * math.sin(tilt)
            z2 = ry * math.sin(tilt) + z1 * math.cos(tilt)
            x2 = x1

            # Perspective projection.
            factor = FOCAL_LENGTH / (FOCAL_LENGTH + z2)
            proj_x = x2 * factor
            proj_y = y2 * factor

            # Translate back to screen coordinates.
            screen_x = proj_x + WIDTH / 2
            screen_y = -proj_y + HEIGHT / 2  # note inversion on y for Pygame
            projected.append((screen_x, screen_y))
        return projected

    def draw(self, screen):
        pts = self.get_projected_vertices()
        # Create a pulsating color for the polygon edges.
        ms = pygame.time.get_ticks()
        pulse = (math.sin(ms / 500) + 1) / 2  # value between 0 and 1
        color = (int(100 + 155 * pulse), int(100 + 155 * (1 - pulse)), 200)
        pygame.draw.polygon(screen, color, pts, 2)

class Ball:
    def __init__(self, icosagon):
        angle = random.uniform(0, 2 * math.pi)
        # Incircle radius = R * cos(π/n)
        incircle = icosagon.radius * math.cos(math.pi / icosagon.sides)
        r = random.uniform(0, incircle)
        self.x = icosagon.center_x + r * math.cos(angle)
        self.y = icosagon.center_y + r * math.sin(angle)
        self.radius = 10
        self.vx = random.uniform(-5, 5)
        self.vy = random.uniform(-5, 5)
        self.gravity = 0.1
        # A random phase offset for the pulsing color.
        self.color_offset = random.uniform(0, 2 * math.pi)

    def update(self):
        self.vy += self.gravity
        self.x += self.vx
        self.y += self.vy

        # Bounce off window edges (fallback if it escapes the polygon)
        if self.x - self.radius < 0 or self.x + self.radius > WIDTH:
            self.vx *= -1
        if self.y - self.radius < 0 or self.y + self.radius > HEIGHT:
            self.vy *= -1

    def draw(self, screen):
        ms = pygame.time.get_ticks()
        pulse = (math.sin(ms / 300 + self.color_offset) + 1) / 2
        # Create a color that cycles in hue by pulsing the red and blue channels.
        color = (int(100 + 155 * pulse),
                 int(100 + 155 * (0.5 + 0.5 * math.sin(ms / 400))),
                 int(100 + 155 * (1 - pulse)))
        pygame.draw.circle(screen, color, (int(self.x), int(self.y)), self.radius)

def point_line_distance(px, py, x1, y1, x2, y2):
    """
    Returns (distance, (nearest_x, nearest_y)) from point (px,py)
    to the line segment between (x1,y1) and (x2,y2).
    """
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1), (x1, y1)
    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = max(0, min(1, t))
    nearest_x = x1 + t * dx
    nearest_y = y1 + t * dy
    dist = math.hypot(px - nearest_x, py - nearest_y)
    return dist, (nearest_x, nearest_y)

def handle_collision(ball, poly):
    """
    Check the ball against each edge of the polygon `poly`
    (a list of vertices in 2-d screen coordinates) and reflect its
    velocity if it penetrates an edge.
    """
    for i in range(len(poly)):
        p1 = poly[i]
        p2 = poly[(i + 1) % len(poly)]
        dist, nearest = point_line_distance(ball.x, ball.y, p1[0], p1[1], p2[0], p2[1])
        if dist < ball.radius:
            # Determine penetration depth.
            penetration = ball.radius - dist
            # Compute the outward normal (from the edge toward the ball center).
            nx = ball.x - nearest[0]
            ny = ball.y - nearest[1]
            n_norm = math.hypot(nx, ny)
            if n_norm == 0:
                continue  # avoid division by zero
            nx /= n_norm
            ny /= n_norm
            # Push the ball out by the penetration depth.
            ball.x += nx * penetration
            ball.y += ny * penetration
            # Reflect the velocity (v = v - 2*(v·n)*n)
            dot = ball.vx * nx + ball.vy * ny
            ball.vx -= 2 * dot * nx
            ball.vy -= 2 * dot * ny

def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Enhanced 3D-Looking Bouncing Balls in a Rotating Icosagon")
    clock = pygame.time.Clock()

    icosa = Icosagon()
    balls = [Ball(icosa) for _ in range(10)]

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        # Update objects.
        icosa.update()
        for ball in balls:
            ball.update()

        # Use the 3D-projected vertices for drawing the polygon.
        poly_proj = icosa.get_projected_vertices()

        # Handle collisions using the original (flat) polygon vertices.
        for ball in balls:
            handle_collision(ball, icosa.vertices)

        # Draw everything.
        screen.fill(BLACK)
        icosa.draw(screen)
        for ball in balls:
            ball.draw(screen)

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()

if __name__ == "__main__":
    main()
