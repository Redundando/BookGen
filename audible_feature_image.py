import os
from cacherator import JSONCache

FEATURED_IMAGE_SIZES = [[0], [0.8], [0.7, 0.7], [0.74, 0.55, 0.55], [0.65, 0.65, 0.65, 0.65], [0.7, 0.42, 0.42, 0.42, 0.42],
        [0.45, 0.45, 0.45, 0.45, 0.45, 0.45]]
FEATURED_IMAGES_POSITIONS = [[(0, 0)], [(0.5, 0.5)], [(0.15, 0.5), (0.85, 0.5)], [(0.5, 0.5), (0.1, 0.5), (0.9, 0.5)],
        [(0.1, 0.9), (0.37, 0.63), (0.63, 0.37), (0.9, 0.1)], [(0.5, 0.5), (0.1, 0.1), (0.1, 0.9), (0.9, 0.1), (0.9, 0.9)],
        [(0.1, 0.05), (0.5, 0.05), (0.9, 0.05), (0.1, 0.95), (0.5, 0.95), (0.9, 0.95)]]

REQUEST_HEADERS = {"User-Agent": "Googlebot/2.1 (+http://www.google.com/bot.html)"}
LOAD_ATTEMPTS = 5

from PIL import ImageDraw, ImageEnhance, ImageFilter
import requests

from PIL import Image
from io import BytesIO


def get_image_from_url(url=""):
    image_data = requests.get(url, headers=REQUEST_HEADERS)
    image = Image.open(BytesIO(image_data.content))
    return image


"""
def get_image_from_audible_url(url=""):
  for i in range(LOAD_ATTEMPTS):
    if i>0:
      print(f" Attempt {i}, waiting {2**(i-1)} seconds for server")
      time.sleep(2**(i-1))
    image = attempt_get_image_from_audible_url(url)
    if image:
      return image
    print(" Attempt failed")
  print(" All attempts failed")
  return None

def get_urls_from_list(list_urls = LIST_URLS):
  return [url.strip() for url in list_urls.split("\n") if url.strip()]
"""


class AudibleImage(JSONCache):

    def __init__(self, image_url=""):
        self.image_url = image_url
        super().__init__(data_id=f"{image_url}", directory="data/images")
        self.image = get_image_from_url(self.image_url)

    @property
    def width(self):
        return self.image.size[0]

    @property
    def height(self):
        return self.image.size[1]

    def resize(self, new_width=500, new_height=None):
        if new_width:
            new_height = int(new_width * self.height / self.width)
        elif new_height:
            new_width = int(new_height * self.height / self.width)
        self.image = self.image.resize((new_width, new_height))

    def crop(self, method="middle", new_width=500, new_height=500):
        (x_1, y_1, x_2, y_2) = (0, 0, new_width, new_height)
        if method == "middle":
            x_1 = int((self.width - new_width) / 2)
            x_2 = x_1 + new_width
            y_1 = int((self.height - new_height) / 2)
            y_2 = y_1 + new_height
        self.image = self.image.crop((x_1, y_1, x_2, y_2))

    def add_corners(self, rad=100):
        circle = Image.new('L', (rad * 2, rad * 2), 0)
        draw = ImageDraw.Draw(circle)
        draw.ellipse((0, 0, rad * 2 - 1, rad * 2 - 1), fill=255)
        alpha = Image.new('L', self.image.size, 255)
        w, h = self.image.size
        alpha.paste(circle.crop((0, 0, rad, rad)), (0, 0))
        alpha.paste(circle.crop((0, rad, rad, rad * 2)), (0, h - rad))
        alpha.paste(circle.crop((rad, 0, rad * 2, rad)), (w - rad, 0))
        alpha.paste(circle.crop((rad, rad, rad * 2, rad * 2)), (w - rad, h - rad))
        self.image.putalpha(alpha)
        return self.image

    def blur(self, radius=5):
        self.image = self.image.filter(ImageFilter.BoxBlur(radius=radius))

    def darken(self, factor=0.5):
        enhancer = ImageEnhance.Brightness(self.image)
        self.image = enhancer.enhance(factor)


def add_drop_shadow(image, radius=10, position=(10, 10)):
    alpha = image.split()[-1]
    alpha_blur = alpha.filter(ImageFilter.BoxBlur(radius))
    shadow = Image.new(mode="RGB", size=alpha_blur.size)
    shadow.putalpha(alpha_blur)
    image_tmp = image.copy()
    image.paste(shadow, position, shadow)
    image.paste(image_tmp, (0, 0), image_tmp)
    return image


def create_audible_feature_image_tuple(
        sources=[], size=(1200, 628), corner_radius=20, shadow_radius=20, shadow_position=(10, 10)):
    size = (size[0] * 2, size[1] * 2)
    num_images = len(sources)
    feature_image_width = size[0]
    feature_image_height = size[1]

    images = sources
    background = images[0]

    image_sizes = FEATURED_IMAGE_SIZES
    image_positions = FEATURED_IMAGES_POSITIONS

    result = Image.new("RGBA", size, 0)
    for i in range(num_images):
        images[i].resize(new_width=int(round(feature_image_height * image_sizes[num_images][i])))

    layers = []
    for image in images:
        image.add_corners(rad=corner_radius)
        layer = Image.new("RGBA", size, 0)
        layers.append(layer)

    for i in range(num_images):
        layers[i].paste(
                images[i].image,
                (round((result.width - images[i].width) * image_positions[num_images][i][0]),
                round((result.height - images[i].height) * image_positions[num_images][i][1])),
                images[i].image)

    for layer in reversed(layers):
        layer = add_drop_shadow(layer, radius=shadow_radius, position=shadow_position)
        result = Image.alpha_composite(result, layer)

    background.image = background.image.rotate(90)
    background.resize(new_width=feature_image_width)
    background.crop(method="middle", new_width=feature_image_width, new_height=feature_image_height)
    background.blur(radius=150)
    if background.image.mode != "RGBA":
        background.image = background.image.convert("RGBA")

    result = Image.alpha_composite(background.image, result)
    result = result.resize((size[0] // 2, size[1] // 2), Image.LANCZOS)

    return result

def save_image(image: Image.Image, filename:str, path: str="data/images/webp", format_:str = "webp"):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
    image.save(f"{path}/{filename}.{format_}")


if __name__ == "__main__":
    ai = AudibleImage(image_url="https://m.media-amazon.com/images/I/41kPHYPbIrL._SL500_.jpg")
    img = create_audible_feature_image_tuple([ai])
    save_image(img, "audible.jpg")
    #print(create_audible_feature_image_tuple([ai]))