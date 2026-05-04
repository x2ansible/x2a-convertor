Puppet::Type.newtype(:redis_health) do
  @doc = 'Monitors Redis instance health and validates expected role.'

  ensurable do
    defaultvalues
    defaultto :present
  end

  newparam(:name, namevar: true) do
    desc 'Unique name for this health check.'
  end

  newparam(:host) do
    desc 'Redis host to connect to.'
    defaultto '127.0.0.1'
  end

  newparam(:port) do
    desc 'Redis port to connect to.'
    defaultto 6379

    validate do |value|
      unless value.to_i.between?(1, 65535)
        raise ArgumentError, "Invalid port: #{value}"
      end
    end

    munge do |value|
      value.to_i
    end
  end

  newparam(:password) do
    desc 'Redis AUTH password.'
    sensitive true
  end

  newparam(:role) do
    desc 'Expected Redis role (master or slave).'
    newvalues(:master, :slave)
  end

  newparam(:interval) do
    desc 'Health check interval in seconds.'
    defaultto 30

    munge do |value|
      value.to_i
    end
  end
end
