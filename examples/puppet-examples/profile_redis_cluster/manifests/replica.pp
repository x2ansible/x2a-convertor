# Replica Redis node configuration.
# Uses PuppetDB to discover the primary node dynamically.
class profile_redis_cluster::replica {

  # PuppetDB query to discover the primary node for this cluster
  $primary_query = puppetdb_query(
    "resources[certname, parameters] {
      type = 'Class' and
      title = 'Profile_redis_cluster::Primary' and
      certname in resources[certname] {
        type = 'Class' and
        title = 'Profile_redis_cluster' and
        parameters.cluster_name = '${profile_redis_cluster::cluster_name}'
      }
    }"
  )

  if empty($primary_query) {
    fail("No primary node found for Redis cluster '${profile_redis_cluster::cluster_name}' in PuppetDB")
  }

  $primary_host = $primary_query[0]['certname']

  # Collect the primary identity file exported by the primary node
  File <<| tag == "redis_primary_${profile_redis_cluster::cluster_name}" |>>

  file { '/etc/redis/redis.conf':
    ensure  => file,
    owner   => 'redis',
    group   => 'redis',
    mode    => '0640',
    content => template('profile_redis_cluster/redis.conf.erb'),
    notify  => Service['redis'],
  }

  # Replica-specific settings
  file { '/etc/redis/conf.d':
    ensure => directory,
    owner  => 'redis',
    group  => 'redis',
    mode   => '0750',
  }

  file { '/etc/redis/conf.d/replica.conf':
    ensure  => file,
    owner   => 'redis',
    group   => 'redis',
    mode    => '0640',
    content => @("EOF")
      # Replica node configuration
      # Managed by Puppet — replicating from ${primary_host}
      replicaof ${primary_host} ${profile_redis_cluster::redis_port}
      masterauth ${profile_redis_cluster::redis_password}
      replica-serve-stale-data yes
      replica-read-only yes
      repl-diskless-sync yes
      repl-diskless-sync-delay 5
      | EOF
    require => File['/etc/redis/conf.d'],
    notify  => Service['redis'],
  }

  service { 'redis':
    ensure    => running,
    enable    => true,
    subscribe => File['/etc/redis/redis.conf'],
  }

  redis_health { 'replica_check':
    host      => '127.0.0.1',
    port      => $profile_redis_cluster::redis_port,
    password  => $profile_redis_cluster::redis_password,
    role      => 'slave',
    interval  => 30,
  }
}
