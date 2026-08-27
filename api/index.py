import sys
import os

# Add the backend directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))

from main import app  # type: ignore[import-not-found]  # resolved via sys.path.append above
from mangum import Mangum

handler = Mangum(app, lifespan="off")
