JEKYLL_IMAGE = minhng/jekyll:4.4.1
# Symlink _includes/deploy exists for GitHub Pages
# Volume mount overrides it locally for better isolation
PROJECT_ROOT = $(shell dirname $(PWD))
JEKYLL_CMD = podman run --rm -ti -p 4000:4000 \
	-v $(PWD):/srv/jekyll:Z,U \
	-v $(PROJECT_ROOT)/deploy:/srv/jekyll/_includes/deploy:Z,U \
	-w /srv/jekyll $(JEKYLL_IMAGE) bash -c

HTMLPROOFER_IMAGE = klakegg/html-proofer:3.19.2

build:
	$(JEKYLL_CMD) "bundle install && bundle exec jekyll build"

serve:
	$(JEKYLL_CMD) "bundle install && bundle exec jekyll serve --baseurl '' --watch -H 0.0.0.0"

check-links:
	$(JEKYLL_CMD) "bundle install && bundle exec jekyll build --baseurl ''"
	podman run --rm -v $(PWD)/_site:/src:Z $(HTMLPROOFER_IMAGE) \
		--allow-hash-href \
		--empty-alt-ignore \
		--disable-external

