# hello_world cookbook

Simple cookbook that supports using Berkshelf and Vagrant.  Good for verifying
your development environment is setup correctly for "[The Berkshelf Way](http://alluvium.com/blog/2013/05/03/the-application-cookbook-pattern-berkshelf-and-team-chef-workflow/)" or for validating new vagrant
boxes.

## Requirements

To run locally, you need Vagrant 1.2.0 or greater installed with the Berkshelf plugin.  For installation information please see the "VAGRANT WITH BERKSHELF" section on [berkshelf.com](http://berkshelf.com/)

## Usage

    cd hello_world
    vagrant up
    vagrant ssh

## Recipes

`hello_world::default` - Logs "Hello, World!" to chef log. Yeah, stupid simple.

## Development

Install the required development gems using:

    bundle

Then the available commands:

    bundle exec thor list


## Contributing

1. Fork it
2. Create your feature branch (`git checkout -b my-new-feature`)
3. Commit your changes (`git commit -am 'Add some feature'`)
4. Push to the branch (`git push origin my-new-feature`)
5. Create new Pull Request

## Author

Author:: caryp (<cary@rightscale.com>)
