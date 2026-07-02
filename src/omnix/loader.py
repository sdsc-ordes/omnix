from os import getenv

from dotenv import load_dotenv
from slims.criteria import equals
from slims.slims import Slims

load_dotenv()
user = getenv("SLIMS_USER")
secret = getenv("SLIMS_SECRET")
slims_url = getenv("SLIMS_URL")
slims_name = getenv("SLIMS_NAME")

slims = Slims(slims_name, slims_url, user, secret)
slims.fetch("ContentType", equals("type", "mouse"))
