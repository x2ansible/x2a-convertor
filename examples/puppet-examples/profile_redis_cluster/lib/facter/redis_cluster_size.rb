Facter.add(:redis_cluster_size) do
  confine kernel: 'Linux'

  setcode do
    begin
      output = Facter::Core::Execution.execute(
        'redis-cli -a "$(cat /etc/redis/.password 2>/dev/null)" --no-auth-warning INFO replication 2>/dev/null'
      )

      if output
        connected = output.lines.select { |l| l.start_with?('slave') || l.start_with?('connected_slaves:') }
        slaves_line = output.lines.find { |l| l.start_with?('connected_slaves:') }

        if slaves_line
          slaves_count = slaves_line.strip.split(':').last.to_i
          slaves_count + 1
        else
          1
        end
      else
        nil
      end
    rescue StandardError
      nil
    end
  end
end
