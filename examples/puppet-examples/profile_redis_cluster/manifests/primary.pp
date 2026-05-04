# Primary Redis node configuration.
# Exports its identity so replicas can discover it via PuppetDB.
class profile_redis_cluster::primary {

  # Export our primary identity for replicas to collect
  @@file { "/etc/redis/cluster_primary_${profile_redis_cluster::cluster_name}":
    ensure  => file,
    content => $facts['networking']['fqdn'],
    tag     => "redis_primary_${profile_redis_cluster::cluster_name}",
  }

  file { '/etc/redis/redis.conf':
    ensure  => file,
    owner   => 'redis',
    group   => 'redis',
    mode    => '0640',
    content => template('profile_redis_cluster/redis.conf.erb'),
    notify  => Service['redis'],
  }

  # Primary-specific settings
  file { '/etc/redis/conf.d/primary.conf':
    ensure  => file,
    owner   => 'redis',
    group   => 'redis',
    mode    => '0640',
    content => @("EOF")
      # Primary node configuration
      # Managed by Puppet
      maxmemory ${profile_redis_cluster::maxmemory_mb}mb
      maxmemory-policy ${profile_redis_cluster::maxmemory_policy}
      hz 10
      dynamic-hz yes
      aof-use-rdb-preamble yes
      | EOF
    notify  => Service['redis'],
  }

  file { '/etc/redis/conf.d':
    ensure => directory,
    owner  => 'redis',
    group  => 'redis',
    mode   => '0750',
    before => File['/etc/redis/conf.d/primary.conf'],
  }

  service { 'redis':
    ensure    => running,
    enable    => true,
    subscribe => File['/etc/redis/redis.conf'],
  }

  # Custom health check resource
  redis_health { 'primary_check':
    host      => '127.0.0.1',
    port      => $profile_redis_cluster::redis_port,
    password  => $profile_redis_cluster::redis_password,
    role      => 'master',
    interval  => 30,
  }
}
