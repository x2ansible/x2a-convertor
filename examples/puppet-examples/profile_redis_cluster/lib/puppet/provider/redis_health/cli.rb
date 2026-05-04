Puppet::Type.type(:redis_health).provide(:cli) do
  desc 'Health check provider using redis-cli.'

  commands redis_cli: 'redis-cli'

  def exists?
    check_health
  end

  def create
    # Health check is stateless — just validates on each run
    check_health
  end

  def destroy
    # Nothing to destroy — health checks are ephemeral
  end

  private

  def check_health
    auth_args = []
    if resource[:password]
      auth_args = ['-a', resource[:password].unwrap]
    end

    begin
      output = redis_cli(
        '-h', resource[:host],
        '-p', resource[:port].to_s,
        *auth_args,
        '--no-auth-warning',
        'INFO', 'replication'
      )

      role_line = output.lines.find { |l| l.start_with?('role:') }
      return false unless role_line

      actual_role = role_line.strip.split(':').last
      expected_role = resource[:role].to_s

      if actual_role != expected_role
        Puppet.warning(
          "Redis health check '#{resource[:name]}': " \
          "expected role '#{expected_role}', got '#{actual_role}'"
        )
        return false
      end

      Puppet.info("Redis health check '#{resource[:name]}': OK (role=#{actual_role})")
      true
    rescue Puppet::ExecutionFailure => e
      Puppet.warning("Redis health check '#{resource[:name]}' failed: #{e.message}")
      false
    end
  end
end
