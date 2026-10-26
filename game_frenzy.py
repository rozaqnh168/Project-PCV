from game.game import Game
if __name__ == "__main__":
    try:
        Game().jalankan()
    except RuntimeError as error:
        print(f"ERROR: {error}")
