# Redis cluster profile — determines node role and applies appropriate config.
# Uses PuppetDB for cross-node discovery and exported resources for
# sentinel coordination.
class profile_redis_cluster (
  String  $cluster_name   = $facts['cluster_name'],
  Integer $redis_port      = 6379,
  Integer $sentinel_port   = 26379,
  String  $redis_password  = 'CHANGEME',
  Integer $maxmemory_mb    = 2048,
  String  $maxmemory_policy = 'allkeys-lru',
  Boolean $sentinel_enabled = true,
) {

  contain profile_redis_cluster::install

  # Determine role from custom fact
  case $facts['redis_role'] {
    'primary': {
      contain profile_redis_cluster::primary

      Class['profile_redis_cluster::install']
      -> Class['profile_redis_cluster::primary']
    }
    'replica': {
      contain profile_redis_cluster::replica

      Class['profile_redis_cluster::install']
      -> Class['profile_redis_cluster::replica']
    }
    default: {
      fail("Unknown redis_role fact value: ${facts['redis_role']}. Expected 'primary' or 'replica'.")
    }
  }

  if $sentinel_enabled {
    contain profile_redis_cluster::sentinel

    Class['profile_redis_cluster::install']
    -> Class['profile_redis_cluster::sentinel']
  }
}
