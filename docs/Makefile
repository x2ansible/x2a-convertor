JEKYLL_IMAGE = minhng/jekyll:4.4.1
JEKYLL_CMD = podman run --rm -ti -v $(PWD):/srv/jekyll:Z,U -w /srv/jekyll $(JEKYLL_IMAGE) bash -c
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

