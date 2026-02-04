# Transformation rules

**Purpose**: Provides a compact reference that language models can consult when converting natural language instructions into Cloudinary transformation strings (the part of the delivery URL between the delivery type and the public ID).

## Rules Usage

* The rules in this document are applicable to the transformation parameters specified in the Cloudinary transformation URL API reference, which can be found here: [https://cloudinary.com/documentation/transformation_reference](https://cloudinary.com/documentation/transformation_reference).  These are the only transformation parameters that Cloudinary officially supports.
* Do not make up parameter names when creating Cloudinary transformations.
* When debugging Cloudinary transformations, check each parameter name carefully with the reference.
* Only use the URL syntax and not the SDK syntax when creating transformations.

## URL Anatomy

Known as the delivery URL or transformation URL, the structure is:

```plain text
https://res.cloudinary.com/<cloud_name>/<asset_type>/<delivery_type>/<transformations>/<version>/<public_id>.<ext>
```

* **asset\_type** `image | video | raw`
* **delivery\_type** usually `upload`, but also `fetch`, `private`, `authenticated`, `facebook`, etc.
* **transformations** one or more transformation components separated by **slashes (`/`)**; inside a component parameters are comma-separated.
* **version** optional (e.g. `v1685472103`) - forces CDN refresh.

### Component template

A component is a comma-separated list of parameters between forward slashes.

```plain text
/<w_??>,<h_??>,<param_X>,<param_Y>,.../
```

For consistency, when creating transformations, order the parameters alphabetically within components, as the SDKs do. If asked about a transformation that isn't ordered alphabetically, there's no need to change it unless you're fixing something that isn't working.

### Parameter types

There are two types of transformation parameters:

* **Action parameters**: Parameters that perform a specific transformation on the asset.
* **Qualifier parameters**: Parameters that do not perform an action on their own, but rather alter the default behavior or otherwise adjust the outcome of the corresponding action parameter.

When creating transformations, first check if the parameter is an action or qualifier.

Include only one action parameter per URL component. Qualifier parameters must be included in the same component as the action parameter that they qualify.

If you want to apply multiple actions in a single transformation URL, apply them in separate chained components, where each action is performed on the result of the previous one.

Assume a parameter is an action parameter unless in the [Transformation Reference](https://cloudinary.com/documentation/transformation_reference) it says, "As a qualifier", "A qualifier that", or "Use with:".

## Core Resize & Crop Parameters

| NLP intent                                                                                         | Cloudinary params              | Notes                                                                                   |
| ----------                                                                                         | -----------------              | -----                                                                                   |
| "resize to 400 x 300"                                                                              | `c_scale,h_300,w_400`          | It's better to specify only one dimension when using c_scale, to keep the aspect ratio. |
| "thumbnail 150 x 150 center crop"                                                                  | `c_thumb,g_center,h_150,w_150` | Thumb is alias for `c_crop` with face & gravity tweaks                                  |
| "square fill 250"                                                                                  | `c_fill,h_250,w_250`           | Fills by cropping; combine with `g_face` or `g_auto`                                    |
| "pad to 800 wide with white"                                                                       | `c_pad,b_white,w_800,`         | Pad adds background                                                                     |
| "keep aspect, max 1000 px"                                                                         | `c_limit,w_1000`               | No upscale                                                                              |
| "crop automatically to certain dimensions, keeping more than a thumbnail crop but less than a fill"| `c_auto,g_auto,w_800`          | Crops and effectively zooms to the most interesting part of the image.                  |

Additional crop modes: `c_crop`, `c_fit`, `c_lfill`, `c_fill_pad`, `c_pad`, `c_imagga_crop`, `c_auto`.

Learn more about [image resizing and cropping](https://cloudinary.com/documentation/resizing_and_cropping) and [video resizing and cropping](https://cloudinary.com/documentation/video_resizing_and_cropping).

## Positioning & Gravity

* `g_center` (default), `g_north_west`, ... cardinals, or `g_xy_center`.
* Smart: `g_auto` (auto-subject), `g_face`, `g_faces`, `g_adv_eyes` (see other [special positions](https://cloudinary.com/documentation/transformation_reference#syntax_g_special_position)).
* Offsets: `x_<pixels>`, `y_<pixels>`.

### Crop modes compatible with g_auto

**Works with g_auto:**

* `c_fill` - Resizes and crops to fill specified dimensions
* `c_lfill` - Same as fill, but only scales down (limit fill)
* `c_fill_pad` - Same as fill, but adds padding when needed (requires g_auto)
* `c_crop` - Extracts a region from the original image
* `c_thumb` - Creates thumbnails with specified gravity
* `c_auto` - Automatically determines the best crop based on gravity
* `c_auto_pad` - Same as auto, but adds padding when needed (requires g_auto)

**Does NOT work with g_auto:**

* `c_scale` - Simple scaling
* `c_fit` - Fit inside bounding box
* `c_limit` - Limit fit (scale down only)
* `c_mfit` - Minimum fit (scale up only)
* `c_pad` - Pad with background color
* `c_lpad` - Limit pad
* `c_mpad` - Minimum pad

Note: `c_fill_pad` and `c_auto_pad` ONLY work with automatic gravity options (`g_auto`).

## Format & Quality

| Param  | Common values                                       | Typical NLP cue                  |
| ------ | --------------------------------------------------- | -------------------------------- |
| `f_`   | `auto`, `jpg`, `png`, `webp`, `avif`, `gif`, `heic` | "convert to webp", "best format" |
| `q_`   | `auto`, `auto:best`, `auto:eco`, `80`, `70:420`     | "optimize", "set quality 80"     |
| `dpr_` | `auto`, `2.0`, `3.0`                                | "Retina"                         |

Automatic optimization of format and quality should be expressed as `f_auto/q_auto` and never `f_auto,q_auto`.

## Visual Effects & Filters (`e_`)

Key effects:

* Color & tone: `e_sepia`, `e_grayscale`, `co_rgb:0044ff,e_colorize:40`, `e_blackwhite`.
* Artistic: `e_cartoonify`, `e_paint:50`, `e_vectorize`, `e_pixelate_faces`.
* Blur & focus: `e_blur:800`, `e_blur_region`, `e_sharpen`.
* Generative: `e_background_removal`, `e_replace_color:blue:50:white`.

Note that `co_` is a qualifier and must be used in the same component as the action that it is qualifying.  For example, to color a text overlay, use `co_` in the same component as `l_text` (e.g. `bo_10px_solid_blue,co_yellow,l_text:Arial_100_bold_italic_stroke_letter_spacing_50:Smile%21/fl_layer_apply,g_south/`).

Syntax: `e_<name>[:param1[:param2...]]`.

See all effects in the [transformation reference](https://cloudinary.com/documentation/transformation_reference#e_effect).

## Overlays & Underlays

```plain text
l_<public_id>/c_scale,fl_relative,w_0.5/g_south,y_20,fl_layer_apply
u_<public_id>/fl_layer_apply
```

* Prefix `l_` overlay ("lay on"), `u_` underlay.
* Add sub-transformations for the overlay by inserting a slash **after** the overlay declaration, then parameters, then complete the overlay with fl_layer_apply in a separate component.  Use positioning parameters in the same component as fl_layer_apply.
* Text overlays: `l_text:<font_family>_<font_size>:<URL-encoded_string>`, plus `co_` (color), `b_` (background), etc.

All overlays (`l_`, `u_` and `l_text`) should follow these conventions:

* A component with `fl_layer_apply` should always end a layer transformation.  Positioning parameters should be included in the `fl_layer_apply` component, and not the layer component. `g_auto` does not work for positioning overlays.
* If including more then one layer, each should end with an `fl_layer_apply` component.

## Borders, Rounding, Background

* Borders: `bo_<width>px_solid_<color>` (e.g. `bo_5px_solid_black`).
* Radius: `r_20` or `r_max` (circle if the dimensions are square).
* Background: `b_rgb:ffffff` or named colors.

If you're intending for a border to follow rounded corners, use border as a qualifier, and therefore put it in the same component as the radius, for example: `c_fill,g_auto,h_400,w_600/r_20,bo_5px_solid_rgb:0066ff/f_png`.

Also consider using the outline effect `e_outline` (e.g. `co_rgb:0066ff,e_outline:outer:15:200`) for borders when an image includes transparency.
See the full syntax for [`e_outline`](https://cloudinary.com/documentation/transformation_reference#e_outline).

When applying a background color together with chained transformations, use the background parameter as a qualifier to a pad crop that doesn't change the dimensions (like `b_lightblue,c_pad,w_1.0`), rather than by itself in a component. Using background in its own component can lead to unpredictable results.

This works (the background turns light blue):

![Convert the transparent areas of an image to the specified color](https://res.cloudinary.com/demo/image/upload/e_background_removal/b_lightblue,c_pad,w_1.0/e_trim/e_gen_restore/docs/cupcake.png "thumb: h_150")

```nodejs
cloudinary.image("docs/cupcake.png", {transformation: [
  {effect: "background_removal"},
  {background: "lightblue", width: "1.0", crop: "pad"},
  {effect: "trim"},
  {effect: "gen_restore"}
  ]})
```

```react
new CloudinaryImage("docs/cupcake.png")
  .effect(backgroundRemoval())
  .resize(
    pad()
      .width("1.0")
      .background(color("lightblue"))
  )
  .reshape(trim())
  .effect(generativeRestore());
```

```vue
new CloudinaryImage("docs/cupcake.png")
  .effect(backgroundRemoval())
  .resize(
    pad()
      .width("1.0")
      .background(color("lightblue"))
  )
  .reshape(trim())
  .effect(generativeRestore());
```

```angular
new CloudinaryImage("docs/cupcake.png")
  .effect(backgroundRemoval())
  .resize(
    pad()
      .width("1.0")
      .background(color("lightblue"))
  )
  .reshape(trim())
  .effect(generativeRestore());
```

```js
new CloudinaryImage("docs/cupcake.png")
  .effect(backgroundRemoval())
  .resize(
    pad()
      .width("1.0")
      .background(color("lightblue"))
  )
  .reshape(trim())
  .effect(generativeRestore());
```

```python
CloudinaryImage("docs/cupcake.png").image(transformation=[
  {'effect': "background_removal"},
  {'background': "lightblue", 'width': "1.0", 'crop': "pad"},
  {'effect': "trim"},
  {'effect': "gen_restore"}
  ])
```

```php
(new ImageTag('docs/cupcake.png'))
 ->effect(Effect::backgroundRemoval())
 ->resize(Resize::pad()->width(1.0)
 ->background(
 Background::color(Color::LIGHTBLUE))
 )
 ->reshape(Reshape::trim())
 ->effect(Effect::generativeRestore());
```

```java
cloudinary.url().transformation(new Transformation()
  .effect("background_removal").chain()
  .background("lightblue").width(1.0).crop("pad").chain()
  .effect("trim").chain()
  .effect("gen_restore")).imageTag("docs/cupcake.png");
```

```ruby
cl_image_tag("docs/cupcake.png", transformation: [
  {effect: "background_removal"},
  {background: "lightblue", width: 1.0, crop: "pad"},
  {effect: "trim"},
  {effect: "gen_restore"}
  ])
```

```csharp
cloudinary.Api.UrlImgUp.Transform(new Transformation()
  .Effect("background_removal").Chain()
  .Background("lightblue").Width(1.0).Crop("pad").Chain()
  .Effect("trim").Chain()
  .Effect("gen_restore")).BuildImageTag("docs/cupcake.png")
```

```dart
cloudinary.image('docs/cupcake.png').transformation(Transformation()
 .effect(Effect.backgroundRemoval())
 .resize(Resize.pad().width('1.0')
 .background(
 Background.color(Color.LIGHTBLUE))
 )
 .reshape(Reshape.trim())
 .effect(Effect.generativeRestore()));
```

```swift
imageView.cldSetImage(cloudinary.createUrl().setTransformation(CLDTransformation()
  .setEffect("background_removal").chain()
  .setBackground("lightblue").setWidth(1.0).setCrop("pad").chain()
  .setEffect("trim").chain()
  .setEffect("gen_restore")).generate("docs/cupcake.png")!, cloudinary: cloudinary)
```

```android
MediaManager.get().url().transformation(new Transformation()
  .effect("background_removal").chain()
  .background("lightblue").width(1.0).crop("pad").chain()
  .effect("trim").chain()
  .effect("gen_restore")).generate("docs/cupcake.png");
```

```flutter
cloudinary.image('docs/cupcake.png').transformation(Transformation()
 .effect(Effect.backgroundRemoval())
 .resize(Resize.pad().width('1.0')
 .background(
 Background.color(Color.LIGHTBLUE))
 )
 .reshape(Reshape.trim())
 .effect(Effect.generativeRestore()));
```

```kotlin
cloudinary.image {
 publicId("docs/cupcake.png")
  effect(Effect.backgroundRemoval())
  resize(Resize.pad() { width(1.0F)
  background(
 Background.color(Color.LIGHTBLUE))
  })
  reshape(Reshape.trim())
  effect(Effect.generativeRestore()) 
}.generate()
```

```jquery
$.cloudinary.image("docs/cupcake.png", {transformation: [
  {effect: "background_removal"},
  {background: "lightblue", width: "1.0", crop: "pad"},
  {effect: "trim"},
  {effect: "gen_restore"}
  ]})
```

```react_native
new CloudinaryImage("docs/cupcake.png")
  .effect(backgroundRemoval())
  .resize(
    pad()
      .width("1.0")
      .background(color("lightblue"))
  )
  .reshape(trim())
  .effect(generativeRestore());
```

This doesn't (the background stays white):

![Don't use the background parameter in its own component with chained transformations](https://res.cloudinary.com/demo/image/upload/e_background_removal/b_lightblue/e_trim/e_gen_restore/docs/cupcake.png "thumb: h_150")

```nodejs
cloudinary.image("docs/cupcake.png", {transformation: [
  {effect: "background_removal"},
  {background: "lightblue"},
  {effect: "trim"},
  {effect: "gen_restore"}
  ]})
```

```react
new CloudinaryImage("docs/cupcake.png")
  .effect(backgroundRemoval())
  .backgroundColor("lightblue")
  .reshape(trim())
  .effect(generativeRestore());
```

```vue
new CloudinaryImage("docs/cupcake.png")
  .effect(backgroundRemoval())
  .backgroundColor("lightblue")
  .reshape(trim())
  .effect(generativeRestore());
```

```angular
new CloudinaryImage("docs/cupcake.png")
  .effect(backgroundRemoval())
  .backgroundColor("lightblue")
  .reshape(trim())
  .effect(generativeRestore());
```

```js
new CloudinaryImage("docs/cupcake.png")
  .effect(backgroundRemoval())
  .backgroundColor("lightblue")
  .reshape(trim())
  .effect(generativeRestore());
```

```python
CloudinaryImage("docs/cupcake.png").image(transformation=[
  {'effect': "background_removal"},
  {'background': "lightblue"},
  {'effect': "trim"},
  {'effect': "gen_restore"}
  ])
```

```php
(new ImageTag('docs/cupcake.png'))
 ->effect(Effect::backgroundRemoval())
 ->backgroundColor(Color::LIGHTBLUE)
 ->reshape(Reshape::trim())
 ->effect(Effect::generativeRestore());
```

```java
cloudinary.url().transformation(new Transformation()
  .effect("background_removal").chain()
  .background("lightblue").chain()
  .effect("trim").chain()
  .effect("gen_restore")).imageTag("docs/cupcake.png");
```

```ruby
cl_image_tag("docs/cupcake.png", transformation: [
  {effect: "background_removal"},
  {background: "lightblue"},
  {effect: "trim"},
  {effect: "gen_restore"}
  ])
```

```csharp
cloudinary.Api.UrlImgUp.Transform(new Transformation()
  .Effect("background_removal").Chain()
  .Background("lightblue").Chain()
  .Effect("trim").Chain()
  .Effect("gen_restore")).BuildImageTag("docs/cupcake.png")
```

```dart
cloudinary.image('docs/cupcake.png').transformation(Transformation()
 .effect(Effect.backgroundRemoval())
 .backgroundColor(Color.LIGHTBLUE)
 .reshape(Reshape.trim())
 .effect(Effect.generativeRestore()));
```

```swift
imageView.cldSetImage(cloudinary.createUrl().setTransformation(CLDTransformation()
  .setEffect("background_removal").chain()
  .setBackground("lightblue").chain()
  .setEffect("trim").chain()
  .setEffect("gen_restore")).generate("docs/cupcake.png")!, cloudinary: cloudinary)
```

```android
MediaManager.get().url().transformation(new Transformation()
  .effect("background_removal").chain()
  .background("lightblue").chain()
  .effect("trim").chain()
  .effect("gen_restore")).generate("docs/cupcake.png");
```

```flutter
cloudinary.image('docs/cupcake.png').transformation(Transformation()
 .effect(Effect.backgroundRemoval())
 .backgroundColor(Color.LIGHTBLUE)
 .reshape(Reshape.trim())
 .effect(Effect.generativeRestore()));
```

```kotlin
cloudinary.image {
 publicId("docs/cupcake.png")
  effect(Effect.backgroundRemoval())
  backgroundColor(Color.LIGHTBLUE)
  reshape(Reshape.trim())
  effect(Effect.generativeRestore()) 
}.generate()
```

```jquery
$.cloudinary.image("docs/cupcake.png", {transformation: [
  {effect: "background_removal"},
  {background: "lightblue"},
  {effect: "trim"},
  {effect: "gen_restore"}
  ]})
```

```react_native
new CloudinaryImage("docs/cupcake.png")
  .effect(backgroundRemoval())
  .backgroundColor("lightblue")
  .reshape(trim())
  .effect(generativeRestore());
```

## Rotation & Flips

* `a_<angle>` (e.g. `a_90`, `a_-20`).
* `a_hflip`, `a_vflip` (or legacy `fl_flip`, `fl_opposite`).

## Flags (`fl_`)

| Flag                       | Meaning                                     |
| -------------------------- | ------------------------------------------- |
| `fl_progressive`           | Progressive JPEG/PNG                        |
| `fl_lossy`                 | Deliver lossy version when converting       |
| `fl_attachment:<filename>` | Force download                              |
| `fl_preserve_transparency` | Don't add white background                  |
| `fl_no_overflow`           | Prevent upscale beyond requested dimensions |
| `fl_immutable_cache`       | Immutable caching                           |
| `fl_region_relative`       | Overlay sizing relative to current region   |

## Variables & Conditionals

Use variables when asked for transformations that are reusable, can be used as templates, or use the same value more than once within a transformation.

### Variables

Variable names can include only alphanumeric characters and must begin with a letter. Variable names must not contain underscores.

* Declare: `$var_250`, `$foo_!bar!` (strings for assigning to variables are written between `!`)
* Use: `w_$var`, `h_$var`
* Arithmetic: `w_div_2`, `h_mul_0.5`
* Variables used in text overlays: `$date_12/l_text:Arial_40:$(date)/fl_layer_apply`

### Conditional Syntax

```plain text
if_<condition>/<transformation>/if_end
if_<condition>/<transformation>/if_else/<else_transformation>/if_end
```

### Supported operators

URL | SDK | symbol | Description  
--- | --- | ---
`eq` | `=` | Equal to
`ne` | `!=` |Not equal to
`lt` | `` |Greater than
`lte`  | `=` |Greater than or equal to
`in`&#124;`nin` | `in`&#124;`nin` | Included in &#124; Not included inCompares a set of strings against another set of strings.

### Common Conditions

* Width: `if_w_gt_300`, `if_w_lte_400`
* Height: `if_h_gt_200`, `if_h_lte_300`
* Aspect ratio: `if_ar_gt_1.0`, `if_ar_lt_3:4`
* Original dimensions: `if_iw_gt_300`, `if_ih_lte_400`
* Tags: `if_!sale!_in_tags`
* Multiple tags: `if_!sale:in_stock!_in_tags`
* Metadata: `if_md:!stock-level!_lt_50`
* Context: `if_ctx:!productType!_eq_!shoes!`

A colon separating strings (within `!`) means AND.

### Multiple Conditions

* AND: `if_w_gt_300_and_h_gt_200`
* OR: `if_w_gt_300_or_h_gt_200`
* AND takes precedence over OR

### Example Patterns

1. **Conditional resize based on width**:

```plain text
if_w_gt_300/c_scale,w_300/if_end
```

1. **Conditional overlay based on tags**:

```plain text
if_!sale!_in_tags/l_sale_icon/fl_layer_apply/if_end
```

1. **Variable-based dimensions**:

```plain text
$width_300/c_fill,h_$width,w_$width
```

1. **Conditional format based on aspect ratio**:

```plain text
if_ar_gt_1.0/f_webp/if_else/f_jpg/if_end
```

1. **Multiple conditions with else**:

```plain text
if_w_gt_300_and_h_gt_200/c_fill,h_200,w_300/if_else/c_pad,h_200,w_300/if_end
```

## Chaining Rules Recap

* Commas **within** a component, slashes **between** components.
* Each component acts on the output of the previous one.
* If no component is supplied, the original asset is delivered as is.
* Format and quality parameters must be in separate components: use `f_auto/q_auto`, never `f_auto,q_auto`.

## Named & Base Transformations

* Define once in console or API, then reference with `t_<name>`.
* Handy for repeatable presets (e.g. `t_thumbnail`).

## Mapping Natural Language - URL (Guidelines for Prompt Builders)

* **Extract dimensions** (numbers + units). -> `w_`, `h_`, choose crop mode.
* **Find format/quality hints** ("webp", "optimize"). -> `f_`, `q_`.
* **Detect focal subject** ("face", "object", positions). -> `g_`.
* **Classify actions** into categories: resize, effect, overlay, optimization.
* **Chain** when sequential logic matters (e.g. crop then rotate then effect).

## Common End-to-End Examples

| Request                                                                                                    | Resulting URL fragment                                                                                                                                                                                                                                                         |
| -------                                                                                                    | ----------------------                                                                                                                                                                                                                                                         |
| "Show me a 300 px circular avatar of Alice, optimized"                                                     | `c_thumb,g_face,h_300,w_300/r_max/f_auto/q_auto`                                                                                                                                                                                                                               |
| "Landscape 1200 wide, add semi-transparent watermark bottom-right"                                         | `c_fit,w_1200/fl_relative,l_logo,opacity_40,w_0.25/fl_layer_apply,g_south_east,x_20,y_20/f_auto/q_auto`                                                                                                                                                                        |
| "Add company logo overlay top-left, 50x50, optimized"                                                      | `l_logo/c_scale,h_50,w_50/fl_layer_apply,g_north_west/f_auto/q_auto`                                                                                                                                                                                                           |
| "Create advent calendar page with date 12, heading 'Christmas Eve', image 'reindeer', and blue background" | `$date_12,$heading_!Christmas%20Eve!,$image_!reindeer!,$bgcolor_!blue!/c_fill,h_800,w_600,b_$bgcolor/l_$image/c_scale,w_0.8/fl_layer_apply,g_center/l_text:Arial_40:$(date)/fl_layer_apply,g_north,y_50/l_text:Arial_60:$(heading)/fl_layer_apply,g_north,y_120/f_auto/q_auto` |

## Gotchas & Best Practices

* Use **`f_auto/q_auto`** at the end of transformations except when the user explicitly asks for a specific format or quality.
* Always separate format and quality parameters with a forward slash: `f_auto/q_auto` is correct, `f_auto,q_auto` is incorrect.
* Prefer **`g_auto`** unless user specifies focal point.
* DPR awareness: for hi-density screens combine `dpr_auto` or vary width via `w_auto:breakpoints`.
* Escape text overlay strings with URL encoding.
* Never use width and height parameters without a cropping mode.  Even though `c_scale` is implied, always state it explicitly.

## Useful References

* Cloudinary [Image Transformations Guide](https://cloudinary.com/documentation/image_transformations) - concepts & examples for images.
* Cloudinary [Video Transformations Guide](https://cloudinary.com/documentation/video_manipulation_and_delivery) - concepts & examples for videos.
* [Transformation URL API Reference](https://cloudinary.com/documentation/transformation_reference) - every parameter, full syntax.
* [Image Resizing & Cropping](https://cloudinary.com/documentation/resizing_and_cropping) deep-dive.
* [Video Resizing & Cropping](https://cloudinary.com/documentation/video_resizing_and_cropping) deep-dive.
* [Variables & Conditional Image Transformations](https://cloudinary.com/documentation/conditional_transformations) reference.
* [Variables & Conditional Video Transformations](https://cloudinary.com/documentation/video_conditional_expressions) reference.
