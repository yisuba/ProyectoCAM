"""Entry point — launch the camera application."""

from interfaz.app import CameraApp


def main():
    app = CameraApp()
    app.mainloop()


if __name__ == "__main__":
    main()
