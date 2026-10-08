
from .core import app
from . import routes
from assets_api import register_assets
from longvideo_api import register_longvideo

register_assets(app)
register_longvideo(app)

__all__ = ["app"]
