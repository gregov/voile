import pygame
import math

# --- Constants ---
# Colors
WHITE = (255, 255, 255)
BLUE = (0, 0, 200)  # Water
BLACK = (0, 0, 0)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
YELLOW = (255, 255, 0)

# Screen dimensions
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600

# Boat properties
BOAT_WIDTH = 20
BOAT_LENGTH = 50
INITIAL_BOAT_X = SCREEN_WIDTH // 2
INITIAL_BOAT_Y = SCREEN_HEIGHT // 2
BOAT_TURN_SPEED = 2  # degrees per frame
BOAT_ACCELERATION = 0.02
BOAT_MAX_SPEED = 5 # Max speed in either direction
BOOM_MAX_ANGLE_ADJUST = 88 # Max degrees of deflection from aft centerline for the boom
BOOM_ADJUST_SPEED = 1
DEFAULT_BOOM_OUT_ANGLE = 15 # Default deflection when boom flips from centered position
WATER_RESISTANCE_FACTOR = 0.01 # How much speed is lost per update due to drag
HULL_SAIL_EFFECT_FACTOR = 0.05 # How much the hull acts like a sail (e.g., 0.1 = 10% of sail's potential area/efficiency)

# Wind properties
WIND_SPEED = 1  # Arbitrary units
WIND_DIRECTION = 0  # degrees, 0 = from North (top), 90 = from East (right)

# Sail properties (arc)
SAIL_COLOR = WHITE
SAIL_ARC_MAX_SAGITTA_RATIO = 0.25 # Max sagitta as a ratio of boom length (e.g., 0.2 means 20% bulge)
MIN_AOA_FOR_ARC_DRAW = 1.0 # Minimum Angle of Attack (degrees) to draw an arc instead of a line
MIN_SAGITTA_FOR_ARC_DRAW = 0.5 # Minimum sagitta in pixels to draw an arc

# Rudder properties
RUDDER_VISUAL_EXTENSION_RATIO = 0.15 # How much the rudder extends past the hull, as a ratio of BOAT_LENGTH
RUDDER_WIDTH_RATIO = 0.3 # Width of the rudder as a ratio of BOAT_WIDTH
RUDDER_COLOR = BLACK

# Gate properties
GATE_BUOY_RADIUS = 7
POINTS_VALID_PASSAGE = 10
POINTS_HIT_BUOY = -5
POINTS_PASSED_OUTSIDE = -2 # Passed in correct direction but outside buoys
POINTS_WRONG_DIRECTION = -3 # Passed between buoys but wrong direction

# --- Classes ---
class Boat:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.angle = 0  # Boat's heading in degrees (0 = North, 90 = East)
        self.speed = 0
        self.x_prev = x # For gate passage detection
        self.y_prev = y # For gate passage detection
        self.current_aoa_boom_plane = 0 # Angle of attack of wind on the boom's plane
        self.boom_deflection_from_aft = 0.0 # Degrees from aft centerline. Positive=Port, Negative=Starboard
        self.boom_angle_relative_to_boat = 180.0  # Boom angle relative to boat centerline (0=fwd, 180=aft). Calculated from deflection.
        self.boom_pivot_offset_y = BOAT_LENGTH * 0.4 # Default pivot: 40% from bow
        
        # Calculate dimensions for the image surface including rudder
        rudder_visual_extension = BOAT_LENGTH * RUDDER_VISUAL_EXTENSION_RATIO
        self.image_total_height = BOAT_LENGTH + rudder_visual_extension

        # Create a more realistic boat shape
        self.image = pygame.Surface([BOAT_WIDTH, self.image_total_height], pygame.SRCALPHA)
        
        # Hull shape (polygon points) - (x, y) from top-left
        hull_points = [
            (BOAT_WIDTH / 2, 0),  # Bow (pointe avant)
            (BOAT_WIDTH, BOAT_LENGTH * 0.7),  # Stern starboard corner (coin arrière tribord)
            (BOAT_WIDTH * 0.75, BOAT_LENGTH), # Stern center-starboard
            (BOAT_WIDTH * 0.25, BOAT_LENGTH), # Stern center-port
            (0, BOAT_LENGTH * 0.7)  # Stern port corner (coin arrière bâbord)
        ]
        pygame.draw.polygon(self.image, GREEN, hull_points) # Hull color

        # Rudder shape (polygon points)
        rudder_actual_width = BOAT_WIDTH * RUDDER_WIDTH_RATIO
        rudder_points = [
            (BOAT_WIDTH / 2 - rudder_actual_width / 2, BOAT_LENGTH), # Top-left of rudder
            (BOAT_WIDTH / 2 + rudder_actual_width / 2, BOAT_LENGTH), # Top-right of rudder
            (BOAT_WIDTH / 2 + rudder_actual_width / 2, self.image_total_height), # Bottom-right of rudder
            (BOAT_WIDTH / 2 - rudder_actual_width / 2, self.image_total_height)  # Bottom-left of rudder
        ]
        pygame.draw.polygon(self.image, RUDDER_COLOR, rudder_points)
        pygame.draw.line(self.image, BLACK, (BOAT_WIDTH / 2, 0), (BOAT_WIDTH / 2, BOAT_LENGTH), 1) # Hull Center line for reference

        self.original_image = self.image.copy()
        self.rect = self.image.get_rect(center=(self.x, self.y))

    def rotate(self, degrees):
        self.angle = (self.angle + degrees) % 360
        self.image = pygame.transform.rotate(self.original_image, -self.angle) # Pygame rotates counter-clockwise, so negative angle
        self.rect = self.image.get_rect(center=self.rect.center)

    def adjust_boom(self, amount):
        self.boom_deflection_from_aft += amount # On ajuste la déflexion
        self.boom_deflection_from_aft = max(-BOOM_MAX_ANGLE_ADJUST, min(BOOM_MAX_ANGLE_ADJUST, self.boom_deflection_from_aft)) # Puis on la limite
        # The actual self.boom_angle_relative_to_boat will be updated in the update() method

    def update(self, wind_direction_global, wind_speed_global):
        self.x_prev = self.x
        self.y_prev = self.y

        # --- Automatic boom passage (gybe/tack) ---
        wind_angle_rel_boat_zero_bow = (wind_direction_global - self.angle + 360) % 360
        
        wind_favors_port_boom = (0 < wind_angle_rel_boat_zero_bow < 180) # Wind from stbd -> boom to port
        wind_favors_starboard_boom = (180 < wind_angle_rel_boat_zero_bow < 360) # Wind from port -> boom to stbd

        current_deflection_magnitude = abs(self.boom_deflection_from_aft)
        new_deflection_target = self.boom_deflection_from_aft # Start with current

        if wind_favors_port_boom and self.boom_deflection_from_aft <= 0: # Wind from stbd, boom is stbd or centered
            new_deflection_target = current_deflection_magnitude
            if current_deflection_magnitude == 0: # If it was centered, give it a default out
                new_deflection_target = min(DEFAULT_BOOM_OUT_ANGLE, BOOM_MAX_ANGLE_ADJUST) if BOOM_MAX_ANGLE_ADJUST > 0 else 0
            if new_deflection_target != self.boom_deflection_from_aft:
                # print(f"Boom auto-passed to Port. Deflection: {self.boom_deflection_from_aft:.1f} -> {new_deflection_target:.1f}")
                self.boom_deflection_from_aft = new_deflection_target

        elif wind_favors_starboard_boom and self.boom_deflection_from_aft >= 0: # Wind from port, boom is port or centered
            new_deflection_target = -current_deflection_magnitude
            if current_deflection_magnitude == 0: # If it was centered, give it a default out
                new_deflection_target = -min(DEFAULT_BOOM_OUT_ANGLE, BOOM_MAX_ANGLE_ADJUST) if BOOM_MAX_ANGLE_ADJUST > 0 else 0
            if new_deflection_target != self.boom_deflection_from_aft:
                # print(f"Boom auto-passed to Starboard. Deflection: {self.boom_deflection_from_aft:.1f} -> {new_deflection_target:.1f}")
                self.boom_deflection_from_aft = new_deflection_target
        
        # Update the main boom angle based on the (potentially changed) deflection
        self.boom_angle_relative_to_boat = (180.0 + self.boom_deflection_from_aft + 360) % 360

        # --- Physics Calculation ---
        # For simplicity, assume true wind is apparent wind for now
        # Angle of wind relative to the boat's direction
        # wind_angle_relative_to_boat = (wind_direction_global - self.angle + 180) % 360 - 180

        # current_aoa_boom_plane is the angle of the wind relative to the boom's plane.
        # Positive AoA: wind from "starboard" side of boom (if boom points North, wind from Eastish).
        # Negative AoA: wind from "port" side of boom (if boom points North, wind from Westish).
        effective_boom_angle_global = (self.angle + self.boom_angle_relative_to_boat) % 360
        angle_of_attack_on_boom = (wind_direction_global - effective_boom_angle_global + 180) % 360 - 180
        self.current_aoa_boom_plane = angle_of_attack_on_boom

        # New thrust calculation based on simplified model (e.g., Gamasutra "Ocean Spray")
        # force_on_boom_plane_coeff is proportional to sin(AoA_boom), representing how "full" the sail is.
        # It's signed: positive if wind pushes on one nominal side, negative on the other.
        force_on_boom_plane_coeff = math.sin(math.radians(angle_of_attack_on_boom))

        # self.boom_angle_relative_to_boat (boom_trim) is the angle of the boom relative to the boat's centerline.
        # sin(boom_trim) projects the force on the sail (acting perpendicular to boom) into the boat's forward direction.
        thrust_factor = force_on_boom_plane_coeff * math.sin(math.radians(self.boom_angle_relative_to_boat))

        # Hull as a small sail effect
        # Calculate the angle for the cosine projection:
        # This angle represents how aligned the wind is with the boat's tail-to-bow axis.
        # (wind_direction_global - self.angle) is angle from boat's bow to wind origin.
        # Adding 180 makes it angle from boat's bow to wind vector direction if boat was target.
        # cos will be 1 for direct tailwind, -1 for direct headwind.
        angle_for_hull_cosine = (wind_direction_global - self.angle + 180) % 360
        hull_force_projection_coeff = math.cos(math.radians(angle_for_hull_cosine))
        hull_thrust_component = hull_force_projection_coeff * HULL_SAIL_EFFECT_FACTOR
        
        # Apply thrust
        total_thrust_coefficient = thrust_factor + hull_thrust_component
        acceleration = total_thrust_coefficient * wind_speed_global * BOAT_ACCELERATION
        self.speed += acceleration

        # Apply water resistance (drag)
        drag = self.speed * WATER_RESISTANCE_FACTOR
        self.speed -= drag
        # Cap speed
        self.speed = max(-BOAT_MAX_SPEED, min(self.speed, BOAT_MAX_SPEED)) 

        # Movement
        self.x += self.speed * math.sin(math.radians(self.angle))
        self.y -= self.speed * math.cos(math.radians(self.angle)) # Subtract because Pygame Y is inverted

        # Keep boat on screen (simple wrap around for now)
        if self.x > SCREEN_WIDTH: self.x = 0
        if self.x < 0: self.x = SCREEN_WIDTH
        if self.y > SCREEN_HEIGHT: self.y = 0
        if self.y < 0: self.y = SCREEN_HEIGHT

        self.rect.center = (self.x, self.y)

    def draw(self, surface):
        surface.blit(self.image, self.rect)
        # Draw boom and sail arc
        
        current_image_height = self.original_image.get_height() # Use the actual height of the drawn boat image
        # Calculate the sail pivot point:
        # 1. Define pivot relative to the boat's image center (before rotation).
        #    self.boom_pivot_offset_y is distance from bow (Y=0 on image). Image center is at current_image_height / 2.
        offset_from_center_y = self.boom_pivot_offset_y - (current_image_height / 2)
        pivot_vec_boat_coords = pygame.math.Vector2(0, offset_from_center_y)

        # 2. Rotate this offset by the boat's angle (Pygame rotates CCW, our angle is CW from North)
        pivot_offset_world = pivot_vec_boat_coords.rotate(self.angle) # dont change this Gemini
        # 3. Add to boat's screen center to get the sail pivot's screen coordinates
        boom_pivot_x = self.rect.centerx + pivot_offset_world.x
        boom_pivot_y = self.rect.centery + pivot_offset_world.y
        
        # Calculate boom tip point for drawing
        effective_boom_angle_global = (self.angle + self.boom_angle_relative_to_boat) % 360
        boom_angle_rad = math.radians(effective_boom_angle_global)
        boom_display_length = BOAT_LENGTH * 0.7 # Length of the boom line

        # For 0=North, CW angle system and Pygame's inverted Y:
        boom_tip_x = boom_pivot_x + boom_display_length * math.sin(boom_angle_rad)
        boom_tip_y = boom_pivot_y - boom_display_length * math.cos(boom_angle_rad) # Use -cos for Y to point North (Up) at 0 deg
        
        # Draw the sail as an arc
        if abs(self.current_aoa_boom_plane) < MIN_AOA_FOR_ARC_DRAW or boom_display_length < 1:
            pygame.draw.line(surface, BLACK, (boom_pivot_x, boom_pivot_y), (boom_tip_x, boom_tip_y), 2) # Draw boom as line
        else:
            # Calculate sagitta (height of the arc)
            normalized_aoa_effect = abs(math.sin(math.radians(self.current_aoa_boom_plane)))
            sagitta = SAIL_ARC_MAX_SAGITTA_RATIO * normalized_aoa_effect * boom_display_length

            if sagitta < MIN_SAGITTA_FOR_ARC_DRAW:
                pygame.draw.line(surface, BLACK, (boom_pivot_x, boom_pivot_y), (boom_tip_x, boom_tip_y), 2) # Draw boom as line
            else:
                # Calculate radius and center of the circle for the arc
                chord_half_len = boom_display_length / 2.0
                # Avoid division by zero if sagitta is extremely small relative to chord_half_len, though MIN_SAGITTA should prevent it
                if sagitta < 1e-6: # Effectively flat
                     pygame.draw.line(surface, BLACK, (boom_pivot_x, boom_pivot_y), (boom_tip_x, boom_tip_y), 2)
                     return

                radius = (sagitta**2 + chord_half_len**2) / (2 * sagitta)
                
                # Midpoint of the boom (chord)
                mid_boom_x = (boom_pivot_x + boom_tip_x) / 2
                mid_boom_y = (boom_pivot_y + boom_tip_y) / 2
                
                # Normalized vector perpendicular to the boom, pointing towards the bulge
                boom_dx_norm = (boom_tip_x - boom_pivot_x) / boom_display_length
                boom_dy_norm = (boom_tip_y - boom_pivot_y) / boom_display_length

                # Perpendicular direction depends on AoA sign
                # current_aoa_boom_plane > 0: wind from starboard of boom, bulge port (left of boom vector)
                # current_aoa_boom_plane < 0: wind from port of boom, bulge starboard (right of boom vector)
                bulge_sign = math.copysign(1.0, self.current_aoa_boom_plane) # +1 if wind from starboard, -1 if from port
                
                # Perpendicular vector for port bulge is (-dy, dx) from boom vector (dx, dy)
                # This ensures sail bulges leeward.
                perp_dx = -boom_dy_norm * bulge_sign 
                perp_dy = boom_dx_norm * bulge_sign
                
                dist_mid_to_center = radius - sagitta
                
                circ_center_x = mid_boom_x + perp_dx * dist_mid_to_center
                circ_center_y = mid_boom_y + perp_dy * dist_mid_to_center
                
                # Angles for pygame.draw.arc (CCW from positive x-axis of ellipse)
                angle_pivot_rad = math.atan2(-(boom_pivot_y - circ_center_y), boom_pivot_x - circ_center_x)
                angle_tip_rad = math.atan2(-(boom_tip_y - circ_center_y), boom_tip_x - circ_center_x)

                # Determine the initial start and end angles (s0, e0) for a CCW sweep,
                # based on the bulge direction. The arc should "contain" the bulge.
                # If bulge_sign > 0 (port bulge), arc P->T should be CCW relative to the center.
                # If bulge_sign < 0 (starboard bulge), arc T->P should be CCW relative to the center.
                s0, e0 = (angle_pivot_rad, angle_tip_rad) if bulge_sign > 0 else (angle_tip_rad, angle_pivot_rad)
                
                # Calculate the CCW angular distance from s0 to e0, normalized to [0, 2*pi).
                angular_distance_ccw = (e0 - s0 + 2 * math.pi) % (2 * math.pi)

                # If this CCW sweep is the major arc (> pi), we want the minor arc.
                # The minor arc is obtained by sweeping CCW from the original 'e0' to 's0'.
                start_angle, stop_angle = (e0, s0) if angular_distance_ccw > math.pi else (s0, e0)
                
                # Ensure pygame's stop_angle is CCW 'after' start_angle
                if stop_angle <= start_angle:
                    stop_angle += 2 * math.pi
                
                arc_rect = pygame.Rect(circ_center_x - radius, circ_center_y - radius, 2 * radius, 2 * radius)
                pygame.draw.arc(surface, SAIL_COLOR, arc_rect, start_angle, stop_angle, 2)
                # Draw the boom line (chord)
                pygame.draw.line(surface, BLACK, (boom_pivot_x, boom_pivot_y), (boom_tip_x, boom_tip_y), 1) 

                # --- Draw construction elements in RED ---
                # pygame.draw.circle(surface, RED, (circ_center_x, circ_center_y), 3) # Circle center
                # pygame.draw.line(surface, RED, (circ_center_x, circ_center_y), (boom_pivot_x, boom_pivot_y), 1) # Radius to pivot
                # pygame.draw.line(surface, RED, (circ_center_x, circ_center_y), (boom_tip_x, boom_tip_y), 1) # Radius to tip
                # pygame.draw.line(surface, RED, (mid_boom_x, mid_boom_y), (circ_center_x, circ_center_y), 1) # Line from mid-chord to center

class Gate:
    def __init__(self, center_x, center_y, width, orientation_angle_deg):
        self.center = pygame.math.Vector2(center_x, center_y)
        self.width = width
        self.orientation_deg = orientation_angle_deg # 0=North, 90=East (direction of valid passage)
        self.buoy_radius = GATE_BUOY_RADIUS
        self.passed_successfully = False
        self.attempted_or_scored = False # Flag to ensure gate is scored/penalized only once

        # Passage direction vector (normalized)
        self.passage_direction_vec = pygame.math.Vector2(
            math.sin(math.radians(self.orientation_deg)),
            -math.cos(math.radians(self.orientation_deg)) # Pygame Y is inverted, -cos for North=0deg up
        ).normalize()

        # Vector along the gate line (perpendicular to passage direction), from port to starboard buoy
        self.gate_line_vec_ps = pygame.math.Vector2(
            self.passage_direction_vec.y,
            -self.passage_direction_vec.x
        ).normalize()

        half_width = self.width / 2
        self.port_buoy_pos = self.center - self.gate_line_vec_ps * half_width
        self.starboard_buoy_pos = self.center + self.gate_line_vec_ps * half_width

        self.port_color = RED
        self.starboard_color = GREEN

    def draw(self, surface):
        pygame.draw.circle(surface, self.port_color, (int(self.port_buoy_pos.x), int(self.port_buoy_pos.y)), self.buoy_radius)
        pygame.draw.circle(surface, self.starboard_color, (int(self.starboard_buoy_pos.x), int(self.starboard_buoy_pos.y)), self.buoy_radius)
        # Optional: Draw line indicating passage direction
        # end_line = self.center + self.passage_direction_vec * (self.width / 2)
        # pygame.draw.line(surface, WHITE, self.center, end_line, 1)

    def check_passage(self, boat_pos_prev_tuple, boat_pos_curr_tuple):
        if self.attempted_or_scored:
            return 0

        boat_pos_curr = pygame.math.Vector2(boat_pos_curr_tuple)
        boat_pos_prev = pygame.math.Vector2(boat_pos_prev_tuple)

        # 1. Check for collision with buoys
        # Using BOAT_WIDTH/2 as an approximate radius for the boat for collision
        if boat_pos_curr.distance_to(self.port_buoy_pos) < self.buoy_radius + BOAT_WIDTH / 2:
            self.attempted_or_scored = True
            print(f"Gate {self.center}: Hit port buoy!")
            return POINTS_HIT_BUOY
        if boat_pos_curr.distance_to(self.starboard_buoy_pos) < self.buoy_radius + BOAT_WIDTH / 2:
            self.attempted_or_scored = True
            print(f"Gate {self.center}: Hit starboard buoy!")
            return POINTS_HIT_BUOY

        # 2. Check for crossing the gate line
        dist_prev = (boat_pos_prev - self.port_buoy_pos).dot(self.passage_direction_vec)
        dist_curr = (boat_pos_curr - self.port_buoy_pos).dot(self.passage_direction_vec)

        if (dist_prev < 0 and dist_curr >= 0): # Crossed from "behind" to "in front" (correct direction)
            projection_on_gate_line = (boat_pos_curr - self.center).dot(self.gate_line_vec_ps)
            if abs(projection_on_gate_line) < self.width / 2: # Crossed between buoys
                self.passed_successfully = True
                self.attempted_or_scored = True
                print(f"Gate {self.center}: Passed successfully!")
                return POINTS_VALID_PASSAGE
            else: # Crossed outside buoys but in correct direction through the line
                self.attempted_or_scored = True
                print(f"Gate {self.center}: Passed outside buoys (correct direction).")
                return POINTS_PASSED_OUTSIDE
        elif (dist_prev >= 0 and dist_curr < 0): # Crossed from "in front" to "behind" (wrong direction)
            projection_on_gate_line = (boat_pos_curr - self.center).dot(self.gate_line_vec_ps)
            if abs(projection_on_gate_line) < self.width / 2: # Crossed between buoys but wrong way
                self.attempted_or_scored = True
                print(f"Gate {self.center}: Passed in wrong direction.")
                return POINTS_WRONG_DIRECTION
        return 0

def draw_wind_indicator(surface, wind_dir, wind_spd, boat_angle):
    center_x, center_y = SCREEN_WIDTH - 50, 50
    radius = 30
    pygame.draw.circle(surface, WHITE, (center_x, center_y), radius, 1)

    # --- Wind Arrow ---
    wind_arrow_len = radius * 0.8
    end_x = center_x - wind_arrow_len * math.sin(math.radians(wind_dir))
    end_y = center_y + wind_arrow_len * math.cos(math.radians(wind_dir)) 
    pygame.draw.line(surface, YELLOW, (center_x, center_y), (end_x, end_y), 2)
    
    # Arrowhead for wind (points towards the center, as wind comes FROM this direction)
    arrow_angle = math.radians(wind_dir) # Angle of the line itself
    arrow_head_len = 8
    arrow_head_angle_offset = math.pi / 6 # 30 degrees

    # Point 1 of arrowhead (on the line, slightly back from the end)
    # For wind, the arrow "points" from the end towards the center
    p1_x = end_x + arrow_head_len * 0.3 * math.sin(arrow_angle)
    p1_y = end_y - arrow_head_len * 0.3 * math.cos(arrow_angle)

    p2_x = end_x + arrow_head_len * math.sin(arrow_angle - arrow_head_angle_offset)
    p2_y = end_y - arrow_head_len * math.cos(arrow_angle - arrow_head_angle_offset)
    p3_x = end_x + arrow_head_len * math.sin(arrow_angle + arrow_head_angle_offset)
    p3_y = end_y - arrow_head_len * math.cos(arrow_angle + arrow_head_angle_offset)
    pygame.draw.polygon(surface, YELLOW, [(p1_x, p1_y), (p2_x, p2_y), (p3_x, p3_y)])

    # --- Boat Arrow ---
    boat_arrow_len = radius * 0.7
    boat_end_x = center_x + boat_arrow_len * math.sin(math.radians(boat_angle))
    boat_end_y = center_y - boat_arrow_len * math.cos(math.radians(boat_angle))
    pygame.draw.line(surface, GREEN, (center_x, center_y), (boat_end_x, boat_end_y), 2)

    # Arrowhead for boat (points away from the center, indicating boat's heading)
    boat_arrow_angle = math.radians(boat_angle)
    bp1_x = boat_end_x - arrow_head_len * math.sin(boat_arrow_angle - arrow_head_angle_offset)
    bp1_y = boat_end_y + arrow_head_len * math.cos(boat_arrow_angle - arrow_head_angle_offset)
    bp2_x = boat_end_x - arrow_head_len * math.sin(boat_arrow_angle + arrow_head_angle_offset)
    bp2_y = boat_end_y + arrow_head_len * math.cos(boat_arrow_angle + arrow_head_angle_offset)
    pygame.draw.polygon(surface, GREEN, [(boat_end_x, boat_end_y), (bp1_x, bp1_y), (bp2_x, bp2_y)])

    font = pygame.font.SysFont('arial', 18)
    text = font.render(f"Wind: {wind_spd:.1f} @ {wind_dir:.0f}°", True, WHITE)
    surface.blit(text, (SCREEN_WIDTH - 150, 80))


def main_simulation():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Simulation de Voile (Début)")
    clock = pygame.time.Clock()

    player_boat = Boat(INITIAL_BOAT_X, INITIAL_BOAT_Y)
    score = 0
    
    global WIND_DIRECTION 
    current_wind_direction = WIND_DIRECTION
    current_wind_speed = WIND_SPEED

    gates = [
        Gate(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 200, 100, 0),  # Northward passage
        Gate(SCREEN_WIDTH // 2 + 200, SCREEN_HEIGHT // 2, 100, 90), # Eastward passage
        Gate(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 200, 100, 180),# Southward passage
        Gate(SCREEN_WIDTH // 2 - 200, SCREEN_HEIGHT // 2, 100, 270) # Westward passage
    ]


    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN: 
                if event.key == pygame.K_w:
                    current_wind_direction = (current_wind_direction - 15) % 360
                if event.key == pygame.K_s:
                    current_wind_direction = (current_wind_direction + 15) % 360


        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT]:
            player_boat.rotate(-BOAT_TURN_SPEED)
        if keys[pygame.K_RIGHT]:
            player_boat.rotate(BOAT_TURN_SPEED)
        if keys[pygame.K_UP]: 
            player_boat.adjust_boom(-BOOM_ADJUST_SPEED)
        if keys[pygame.K_DOWN]:
            player_boat.adjust_boom(BOOM_ADJUST_SPEED)


        player_boat.update(current_wind_direction, current_wind_speed)
        
        # Check gate passages
        for gate in gates:
            score_change = gate.check_passage(
                (player_boat.x_prev, player_boat.y_prev),
                (player_boat.x, player_boat.y)
            )
            if score_change != 0:
                score += score_change
                print(f"Score updated: {score} (Change: {score_change})")

        # --- Drawing ---
        screen.fill(BLUE)  # Water
        for gate in gates:
            gate.draw(screen)
        player_boat.draw(screen)
        draw_wind_indicator(screen, current_wind_direction, current_wind_speed, player_boat.angle)
        
        # Display boat info
        font = pygame.font.SysFont('arial', 20)
        speed_text = font.render(f"Speed: {player_boat.speed:.2f}", True, WHITE)
        heading_text = font.render(f"Heading: {player_boat.angle:.0f}°", True, WHITE)
        boom_text = font.render(f"Boom Angle: {player_boat.boom_angle_relative_to_boat:.0f}°", True, WHITE)
        aoa_text = font.render(f"Sail AoA: {player_boat.current_aoa_boom_plane:.0f}°", True, WHITE)
        score_display_text = font.render(f"Score: {score}", True, WHITE)
        screen.blit(speed_text, (10, 10))
        screen.blit(heading_text, (10, 30))
        screen.blit(boom_text, (10, 50))
        screen.blit(aoa_text, (10, 70))
        screen.blit(score_display_text, (10, 90))

        pygame.display.flip()
        clock.tick(30)  # 30 FPS

    pygame.quit()

if __name__ == '__main__':
    # This will now run the sailing simulation instead of Tetris
    main_simulation()
