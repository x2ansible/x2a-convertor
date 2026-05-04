Facter.add(:redis_role) do
  confine kernel: 'Linux'

  setcode do
    config_file = '/etc/redis/conf.d/replica.conf'
    if File.exist?(config_file) && File.read(config_file).include?('replicaof')
      'replica'
    else
      'primary'
    end
  end
end
