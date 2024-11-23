import os
import pstats

def read_profiler_files(profile_dir='./profiler'):
    if not os.path.exists(profile_dir):
        print(f"The directory {profile_dir} does not exist.")
        return
    
    files = [f for f in os.listdir(profile_dir) if f.endswith('.prof')]
    
    if not files:
        print(f"No .prof files found in {profile_dir}.")
        return

    for file in files:
        filepath = os.path.join(profile_dir, file)
        
        try:
            # Use Stats directly with the file path (not opening in binary mode)
            stats = pstats.Stats(filepath)
            stats.strip_dirs()  # Optionally strip directory paths for readability
            stats.sort_stats('time')  # Sort by time (can change to 'cumulative', etc.)
            stats.sort_stats('time')  # Sort by time taken to execute
            print(f"Contents of {file}:")
            stats.print_stats(20) 
            print("=" * 80)
        except Exception as e:
            print(f"Error reading {file}: {e}")

if __name__ == "__main__":
    read_profiler_files('./performance_profiler/customer')
    read_profiler_files('./performance_profiler/inventory')