# Redis Sentinel configuration with exported resources.
# Each sentinel node exports its config; all sentinels collect from each other.
class profile_redis_cluster::sentinel {

  $primary_query = puppetdb_query(
    "resources[certname] {
      type = 'Class' and
      title = 'Profile_redis_cluster::Primary' and
      certname in resources[certname] {
        type = 'Class' and
        title = 'Profile_redis_cluster' and
        parameters.cluster_name = '${profile_redis_cluster::cluster_name}'
      }
    }"
  )

  $primary_host = $primary_query[0]['certname']

  # Export our sentinel endpoint for other sentinel nodes to collect
  @@host { "sentinel-${facts['networking']['fqdn']}":
    ensure       => present,
    ip           => $facts['networking']['ip'],
    host_aliases => ["sentinel-${facts['networking']['hostname']}"],
    tag          => "redis_sentinel_${profile_redis_cluster::cluster_name}",
  }

  # Collect all sentinel endpoints from the cluster
  Host <<| tag == "redis_sentinel_${profile_redis_cluster::cluster_name}" |>>

  # Query PuppetDB for all sentinel nodes in this cluster to build quorum
  $sentinel_nodes = puppetdb_query(
    "resources[certname] {
      type = 'Class' and
      title = 'Profile_redis_cluster::Sentinel' and
      certname in resources[certname] {
        type = 'Class' and
        title = 'Profile_redis_cluster' and
        parameters.cluster_name = '${profile_redis_cluster::cluster_name}'
      }
    }"
  )

  $quorum = max(1, size($sentinel_nodes) / 2 + 1)

  file { '/etc/redis/sentinel.conf':
    ensure  => file,
    owner   => 'redis',
    group   => 'redis',
    mode    => '0640',
    content => template('profile_redis_cluster/sentinel.conf.erb'),
    notify  => Service['redis-sentinel'],
  }

  service { 'redis-sentinel':
    ensure => running,
    enable => true,
  }
}
