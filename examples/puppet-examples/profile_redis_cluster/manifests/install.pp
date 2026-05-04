# Install Redis using the external puppet-redis module.
class profile_redis_cluster::install {

  # Use external puppet-redis module for package management
  class { 'redis':
    bind       => '0.0.0.0',
    port       => $profile_redis_cluster::redis_port,
    appendonly => true,
    appendfsync => 'everysec',
  }

  # Health check script
  file { '/usr/local/bin/redis-check.sh':
    ensure => file,
    source => 'puppet:///modules/profile_redis_cluster/redis-check.sh',
    owner  => 'root',
    group  => 'root',
    mode   => '0755',
  }

  # Ensure log directory exists
  file { '/var/log/redis':
    ensure => directory,
    owner  => 'redis',
    group  => 'redis',
    mode   => '0755',
  }

  # HACK: Clean up default config entries that conflict with cluster setup.
  # The puppet-redis module adds replica settings even for primary nodes.
  ruby_block 'cleanup_redis_default_config' do
    block_content => <<-'RUBY'
      config_file = '/etc/redis/redis.conf'
      if File.exist?(config_file)
        content = File.read(config_file)
        content.gsub!(/^replica-serve-stale-data.*\n/, '')
        content.gsub!(/^replica-read-only.*\n/, '')
        content.gsub!(/^repl-ping-replica-period.*\n/, '')
        File.write(config_file, content)
      end
    RUBY
    require => Class['redis'],
  }
}
