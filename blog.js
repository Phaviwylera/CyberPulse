document.addEventListener('DOMContentLoaded', () => {
    const postContainer = document.getElementById('post-list-container');

    fetch('blog-index.json')
        .then(response => response.json())
        .then(posts => {
            if (posts.length === 0) {
                postContainer.innerHTML = '<p>No posts found.</p>';
                return;
            }
            
            let allPostsHTML = '';
            posts.forEach(post => {
                allPostsHTML += `
                    <a href="${post.url}" class="post-link">
                        <h2>${post.title}</h2>
                        <p>${post.summary}</p>
                    </a>
                `;
            });
            postContainer.innerHTML = allPostsHTML;
        })
        .catch(error => {
            console.error('Error fetching blog index:', error);
            postContainer.innerHTML = '<p>Error loading posts.</p>';
        });
});