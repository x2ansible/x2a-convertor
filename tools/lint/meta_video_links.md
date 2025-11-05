# meta-video-links

Video links must be dictionaries with `url` and `title` keys, and the `url` must be from YouTube, Vimeo, or Google Drive.

## Problematic code

```yaml
galaxy_info:
  video_links:
    # Missing url key
    - https://www.youtube.com/watch?v=aWmRepTSFKs

    # Wrong key name
    - my_bad_key: https://www.youtube.com/watch?v=aWmRepTSFKs
      title: Incorrect key

    # Unsupported URL format
    - url: www.acme.com/vid
      title: Incorrect url format
```

## Correct code

```yaml
galaxy_info:
  video_links:
    - url: https://www.youtube.com/watch?v=aWmRepTSFKs&feature=youtu.be
      title: Correctly formatted video link
```
