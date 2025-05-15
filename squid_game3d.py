Python 3.12.10 (tags/v3.12.10:0cc8128, Apr  8 2025, 12:21:36) [MSC v.1943 64 bit (AMD64)] on win32
Enter "help" below or click "Help" above for more information.
from direct.showbase.ShowBase import ShowBase
from panda3d.core import AmbientLight, DirectionalLight, LColor, CardMaker, TextNode
from direct.gui.DirectGui import DirectLabel
import sys, os
from direct.task import Task

class SquidGameScene(ShowBase):
    def __init__(self):

        ShowBase._init_(self)
        self.disableMouse()

        # ------------------------------
        # 1. Basic Lighting Setup
        # ------------------------------
        ambient = AmbientLight("ambientLight")
        ambient.setColor((0.8, 0.8, 0.8, 1))
        self.render.setLight(self.render.attachNewNode(ambient))
        
        directional = DirectionalLight("directionalLight")
        directional.setColor((0.9, 0.9, 0.9, 1))
        dlnp = self.render.attachNewNode(directional)
        dlnp.setHpr(45, -45, 0)
        self.render.setLight(dlnp)
        
        # ------------------------------
        # 2. Load Skybox (Optional)
        # ------------------------------
        skybox_path = "my_skybox.glb"
        if os.path.isfile(skybox_path):
            self.skybox = self.loader.loadModel(skybox_path)
            self.skybox.reparentTo(self.render)
            self.skybox.setScale(1000)
            self.skybox.setLightOff()
            self.skybox.setCompass()
        else:
            print(f"[WARN] Skybox file '{skybox_path}' not found!")
        
        # ------------------------------
        # 3. Load Characters
        # ------------------------------
        self.doll = self.load_model("squid_game_doll.glb", (0, 60, 0), scale=2)
        self.doll.setHpr(0, 0, 0)  # Doll initially faces players

        self.guard = self.load_model("squid_game_guard2.glb", (-4, 60, 0), scale=2)
        
        # Two players at the starting point (Y=0)
        self.player1 = self.load_model("player1.glb", (-3, 0, 0), scale=2)
        self.player2 = self.load_model("player2.glb", (3, 0, 0), scale=2)
        
        # Make players face the doll visually (apply lookAt then a 180° offset).
        self.inverted_heading = {}
        for p in [self.player1, self.player2]:
            p.lookAt(self.doll)
            hpr = p.getHpr()
            p.setHpr(hpr[0] + 180, hpr[1], hpr[2])
            self.inverted_heading[p] = True

        self.players = [self.player1, self.player2]
        self.player_alive = {p: True for p in self.players}
        # NEW: List for eliminated players (not yet picked up by the guard)
        self.dead_players = []
        
        # ------------------------------
        # 4. Create Finish Line (Visual)
        # ------------------------------
        self.finish_line_y = 60  # When a player reaches Y>=60, they win.
        cm = CardMaker("finish_line")
        cm.setFrame(-5, 5, 0, 0.2)  # A thin, horizontal card 10 units wide
        self.finish_line = self.render.attachNewNode(cm.generate())
        self.finish_line.setPos(0, self.finish_line_y, 0)
        self.finish_line.setColor(1, 0, 0, 1)  # Red finish line
        print("[DEBUG] Finish line created at Y =", self.finish_line_y)
        
        # ------------------------------
        # 5. Camera Setup
        # ------------------------------
        self.camera.setPos(0, -30, 10)
        self.camera.lookAt(0, 30, 0)
        
        # ------------------------------
        # 6. Game Logic Setup
        # ------------------------------
        self.game_state = "red"  # Start with Red Light
        self.red_sfx   = self.load_audio("red_light.mp3")
        self.green_sfx = self.load_audio("green_light.mp3")
        
        # Toggle lights every 3 seconds
        self.taskMgr.doMethodLater(3, self.update_game, "updateGame")
        
        # 1-minute overall timer
        self.total_time = 60  # seconds
        self.taskMgr.add(self.update_timer, "updateTimer")
        
        # Check winners / game over
        self.taskMgr.add(self.check_for_winners, "checkWinners")
        
        # Player 1 keys
        self.accept("f", self.move_player, [self.player1, 1, 0])
        self.accept("b", self.move_player, [self.player1, -1, 0])
        self.accept("l", self.move_player, [self.player1, 0, -1])
        self.accept("r", self.move_player, [self.player1, 0, 1])
        
        # Player 2 keys
        self.accept("arrow_up",    self.move_player, [self.player2, 1, 0])
        self.accept("arrow_down",  self.move_player, [self.player2, -1, 0])
        self.accept("arrow_left",  self.move_player, [self.player2, 0, -1])
        self.accept("arrow_right", self.move_player, [self.player2, 0, 1])
        
        # ------------------------------
        # 7. On-Screen UI (Timer Only)
        # ------------------------------
        self.timer_label = DirectLabel(
            text="Time Left: 60", scale=0.1, pos=(0.0, 0, 0.9),
            text_fg=(1, 1, 1, 1), text_align=TextNode.ACenter
        )
        
        # ------------------------------
        # 8. Exit Setup
        # ------------------------------
        self.accept("escape", sys.exit)
        
        # ------------------------------
        # NEW: Guard Chase Task for dead players
        # ------------------------------
        self.taskMgr.add(self.guard_chase, "guardChase")
        
    # --------------------------------------------------
    # HELPER FUNCTIONS
    # --------------------------------------------------
    def load_model(self, path, pos=(0, 0, 0), scale=1):
        """Load a model and place it in the world."""
        if os.path.isfile(path):
            model = self.loader.loadModel(path)
            model.reparentTo(self.render)
            model.setScale(scale)
            model.setPos(*pos)
            return model
        else:
            print(f"[ERROR] Model file '{path}' not found!")
            sys.exit(1)

    def load_audio(self, path):
        """Load an audio file if it exists, otherwise return None."""
        if os.path.isfile(path):
            return self.loader.loadSfx(path)
        else:
            print(f"[WARN] Audio file '{path}' not found!")
            return None
        
    # --------------------------------------------------
    # GAME LOGIC
    # --------------------------------------------------
    def move_player(self, player, fb=0, lr=0):
        """
        Move the player regardless of light state.
        If game_state is green, they move safely.
        If game_state is red, they move and are immediately eliminated.
        """
        if self.player_alive[player]:
            speed = 0.3
            if self.inverted_heading.get(player, False):
                fb = -fb
            player.setY(player, fb * speed)
            player.setX(player, lr * speed)
            if self.game_state == "red":
                print(f"💀 {player} moved during red light! Eliminated!")
                self.eliminate_player(player)
                
    def eliminate_player(self, player):
        """Eliminate the player by making them 'fall down' (pitch -90) and add to dead_players list."""
        self.player_alive[player] = False
        # Animate falling down using a simple pitch change
        player.setP(-90)
        self.dead_players.append(player)
        
    def update_game(self, task):
        """Toggle Red/Green Light every 3 seconds."""
        if self.game_state == "red":
            self.game_state = "green"
            print("🚦 Green Light! Run!")
            if self.green_sfx:
                self.green_sfx.play()
            self.doll.setHpr(180, 0, 0)  # Doll's back to players
        else:
            self.game_state = "red"
            print("🚦 Red Light! Stop!")
            if self.red_sfx:
                self.red_sfx.play()
            self.doll.setHpr(0, 0, 0)    # Doll faces players
        return task.again

    def update_timer(self, task):
        """Decrement the 1-minute timer. If it hits 0, game over."""
        dt = globalClock.getDt()
        self.total_time -= dt
        if self.total_time < 0:
            self.total_time = 0
            print("Time's Up! Game Over!")
            sys.exit(0)
        self.timer_label["text"] = f"Time Left: {int(self.total_time)}"
        return Task.cont

    def check_for_winners(self, task):
        """Check if any alive player has crossed the finish line."""
        all_dead = True
        for player in self.players:
            if self.player_alive[player]:
                all_dead = False
                y_pos = player.getY(self.render)
                if y_pos >= self.finish_line_y:
                    print(f"🏆 {player} has reached the doll and wins!")
                    self.player_alive[player] = False
        if all_dead:
...             print("Game Over! All players have been eliminated or have won.")
...             sys.exit(0)
...         return Task.cont
... 
...     def guard_chase(self, task):
...         """
...         If any player is dead (eliminated) but not yet picked up,
...         the guard moves toward the closest dead player. When close,
...         the guard 'picks them up' by moving them aside.
...         """
...         chase_speed = 2.0  # units per second
...         if self.dead_players:
...             # Find the closest dead player
...             guard_pos = self.guard.getPos()
...             target = min(self.dead_players, key=lambda p: (p.getPos() - guard_pos).length())
...             direction = target.getPos() - guard_pos
...             if direction.length() != 0:
...                 direction.normalize()
...                 new_pos = guard_pos + direction * chase_speed * globalClock.getDt()
...                 self.guard.setPos(new_pos)
...             # If guard is close to the dead player, pick them up (move them aside)
...             if (target.getPos() - self.guard.getPos()).length() < 2.0:
...                 # Move the dead player aside; for example, if their x < 0, move to x = -20, else x = 20.
...                 target_pos = target.getPos()
...                 if target_pos.getX() < 0:
...                     target.setPos(-20, target_pos.getY(), target_pos.getZ())
...                 else:
...                     target.setPos(20, target_pos.getY(), target_pos.getZ())
...                 print(f"{target} has been picked up by the guard and moved aside.")
...                 self.dead_players.remove(target)
...         return Task.cont
... 
... if __name__ == "__main__":
... 
...     game = SquidGameScene()
